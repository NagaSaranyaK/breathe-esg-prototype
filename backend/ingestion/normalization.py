"""
Normalization Engine — Breathe ESG Mini-Ingest Portal

Converts raw CSV rows from three enterprise source systems into standardised
NormalizedEmissionRow records expressed in Metric Tons CO2 Equivalent (MTCO2e).

Emission formula:
    co2e_mt = activity_value × emission_factor

Sources:
    SAP Fuel & Procurement  → Scope 1  (direct combustion)
    Utility Electricity     → Scope 2  (purchased energy)
    Corporate Travel        → Scope 3  (value chain)
"""

import csv
import io
from datetime import date
from decimal import Decimal, InvalidOperation

# ── Emission Factors ─────────────────────────────────────────────────────────

# Material number prefix → (fuel_label, MTCO2e/Liter, unit_label)
MATERIAL_FUEL_MAP = {
    "DIESEL":   ("diesel",   Decimal("0.002701"), "MTCO2e/L"),
    "PETROL":   ("petrol",   Decimal("0.002289"), "MTCO2e/L"),
    "GASOLINE": ("petrol",   Decimal("0.002289"), "MTCO2e/L"),
    "LPG":      ("lpg",      Decimal("0.001542"), "MTCO2e/L"),
}

# Electricity: US EPA eGRID average 2024
ELECTRICITY_FACTOR      = Decimal("0.000386")   # MTCO2e/kWh
ELECTRICITY_FACTOR_UNIT = "MTCO2e/kWh"

# Aviation: economy baseline, adjusted upward by cabin class multiplier
FLIGHT_BASE_FACTOR      = Decimal("0.000255")   # MTCO2e/mile (economy)
FLIGHT_FACTOR_UNIT      = "MTCO2e/mile"

# Spend-based fallback when DISTANCE_MILES is absent but NET_COST is present
SPEND_FACTOR            = Decimal("0.0008")     # MTCO2e/USD
SPEND_FACTOR_UNIT       = "MTCO2e/USD"

# Hotel accommodation (DEFRA 2024, UK average per room-night)
HOTEL_FACTOR            = Decimal("0.0000617")
HOTEL_FACTOR_UNIT       = "MTCO2e/room-night"

# Ground transport factors (DEFRA 2024, MTCO2e/mile)
GROUND_FACTORS = {
    "car rental":  (Decimal("0.000168"),   "MTCO2e/mile"),
    "rental car":  (Decimal("0.000168"),   "MTCO2e/mile"),
    "taxi":        (Decimal("0.000211"),   "MTCO2e/mile"),
    "rideshare":   (Decimal("0.000211"),   "MTCO2e/mile"),
    "train":       (Decimal("0.0000041"),  "MTCO2e/mile"),
    "rail":        (Decimal("0.0000041"),  "MTCO2e/mile"),
    "bus":         (Decimal("0.0000089"),  "MTCO2e/mile"),
    "ferry":       (Decimal("0.000113"),   "MTCO2e/mile"),
}

# Cabin class multipliers relative to economy baseline
CABIN_MULTIPLIERS = {
    "economy":         Decimal("1.0"),
    "premium economy": Decimal("1.5"),
    "business":        Decimal("2.0"),
    "first":           Decimal("2.5"),
}

# SAP unit-of-measure codes → conversion factor to Liters
UNIT_TO_LITERS = {
    "L":      Decimal("1"),
    "LTR":    Decimal("1"),
    "LITER":  Decimal("1"),
    "LITERS": Decimal("1"),
    "KL":     Decimal("1000"),
    "KLT":    Decimal("1000"),
    "GAL":    Decimal("3.785411784"),
    "M3":     Decimal("1000"),
}

# Flagging thresholds — rows with activity_value above these are suspicious
FLAG_THRESHOLDS = {
    "SAP_FUEL":            Decimal("50000"),    # liters
    "UTILITY_ELECTRICITY": Decimal("500000"),   # kWh
    "CORPORATE_TRAVEL":    Decimal("20000"),    # miles
}


# ── Helpers ──────────────────────────────────────────────────────────────────

def _safe_decimal(value, field_name="value"):
    """Return (Decimal, None) on success or (None, error_string) on failure."""
    try:
        return Decimal(str(value).strip()), None
    except (InvalidOperation, TypeError, ValueError):
        return None, f"Invalid numeric value for {field_name}: '{value}'"


def _parse_date(value, field_name="date"):
    """Return (date, None) on success, (None, None) if blank, (None, error) on bad format."""
    if not value or not str(value).strip():
        return None, None
    try:
        return date.fromisoformat(str(value).strip()), None
    except ValueError:
        return None, f"Invalid date format for {field_name}: '{value}'"


# ── Parser: SAP Fuel & Procurement ───────────────────────────────────────────

def parse_sap_row(row, log, row_model):
    """
    Maps a SAP Fuel CSV row to a NormalizedEmissionRow (Scope 1).

    Key columns:
        MATERIAL_ID  — Material ID (prefix determines fuel type)
        QUANTITY     — Quantity
        UNIT         — Unit of measure (L, KL, GAL …)
        DOC_DATE, PLANT_CODE, DESCRIPTION — metadata for description/reference
    """
    from .models import EmissionStatus, EmissionScope, SourceType

    raw = dict(row)
    flags = []

    # Resolve fuel type from MATERIAL_ID prefix
    material_id = str(raw.get("MATERIAL_ID", "")).strip().upper()
    fuel_type = emission_factor = factor_unit = None

    for prefix, (ftype, factor, funit) in MATERIAL_FUEL_MAP.items():
        if material_id.startswith(prefix):
            fuel_type, emission_factor, factor_unit = ftype, factor, funit
            break

    if not fuel_type:
        fuel_type = "diesel"
        emission_factor = MATERIAL_FUEL_MAP["DIESEL"][1]
        factor_unit     = MATERIAL_FUEL_MAP["DIESEL"][2]
        if material_id:
            flags.append(f"Unknown material '{material_id}' — defaulted to diesel emission factor")

    # Parse quantity
    quantity_raw = str(raw.get("QUANTITY", "")).strip()
    if not quantity_raw:
        flags.append("Missing required field: QUANTITY")
        quantity = None
    else:
        quantity, err = _safe_decimal(quantity_raw, "QUANTITY")
        if err:
            flags.append(err)
            quantity = None
        elif quantity <= 0:
            flags.append(f"Zero or negative quantity: {quantity}")
            quantity = None

    # Convert to litres
    unit       = str(raw.get("UNIT", "L")).strip().upper()
    conversion = UNIT_TO_LITERS.get(unit, Decimal("1"))

    activity_value = co2e_mt = None
    if quantity is not None:
        activity_value = (quantity * conversion).quantize(Decimal("0.0001"))
        if activity_value > FLAG_THRESHOLDS["SAP_FUEL"]:
            flags.append(f"Unusually high fuel quantity: {activity_value} L")
        co2e_mt = (activity_value * emission_factor).quantize(Decimal("0.000001"))

    # Build reference and description
    doc_date         = raw.get("DOC_DATE", "")
    plant_code       = raw.get("PLANT_CODE", "")
    source_reference = f"{doc_date}-{plant_code}-{material_id}".strip("-")
    desc             = raw.get("DESCRIPTION", material_id)
    description      = f"{desc} ({plant_code})" if plant_code else desc

    normalized = {
        "quantity_liters":   float(activity_value) if activity_value else None,
        "fuel_type":         fuel_type,
        "original_unit":     unit,
        "conversion_factor": float(conversion),
    }

    status = (
        EmissionStatus.FLAGGED
        if flags else EmissionStatus.PENDING
    )

    return row_model(
        tenant_id=log.tenant_id,
        ingestion_log_id=log.id,
        source_type=SourceType.SAP_FUEL,
        scope=EmissionScope.SCOPE_1,
        description=description,
        source_reference=source_reference,
        raw_source_data=raw,
        normalized_data=normalized,
        activity_value=activity_value,
        activity_unit="L",
        emission_factor=emission_factor,
        emission_factor_unit=factor_unit,
        co2e_mt=co2e_mt,
        status=status,
        flag_reason="; ".join(flags) if flags else None,
    )


# ── Parser: Utility Electricity ───────────────────────────────────────────────

def parse_utility_row(row, log, row_model):
    """
    Maps a utility portal CSV row to a NormalizedEmissionRow (Scope 2).

    Key columns:
        USAGE_KWH                    — electricity consumed
        SERVICE_START / SERVICE_END  — billing period (rarely calendar-aligned)
        METER_ID                     — source reference
    """
    from .models import EmissionStatus, EmissionScope, SourceType

    raw = dict(row)
    flags = []

    # Parse usage
    usage_raw = str(raw.get("USAGE_KWH", "")).strip()
    if not usage_raw:
        flags.append("Missing required field: USAGE_KWH")
        usage_kwh = None
    else:
        usage_kwh, err = _safe_decimal(usage_raw, "USAGE_KWH")
        if err:
            flags.append(err)
            usage_kwh = None
        elif usage_kwh <= 0:
            flags.append(f"Zero or negative electricity usage: {usage_kwh} kWh")
            usage_kwh = None

    activity_value = co2e_mt = None
    if usage_kwh is not None:
        activity_value = usage_kwh.quantize(Decimal("0.0001"))
        if activity_value > FLAG_THRESHOLDS["UTILITY_ELECTRICITY"]:
            flags.append(f"Unusually high electricity usage: {activity_value} kWh")
        co2e_mt = (activity_value * ELECTRICITY_FACTOR).quantize(Decimal("0.000001"))

    # Billing period
    period_start, err = _parse_date(raw.get("SERVICE_START"), "SERVICE_START")
    if err:
        flags.append(err)
    period_end, err = _parse_date(raw.get("SERVICE_END"), "SERVICE_END")
    if err:
        flags.append(err)

    meter_id         = str(raw.get("METER_ID", "")).strip()
    source_reference = meter_id
    description      = f"Electricity — meter {meter_id}" if meter_id else "Electricity"

    normalized = {
        "usage_kwh":       float(usage_kwh) if usage_kwh else None,
        "grid_region":     "US_AVG",
        "emission_factor": float(ELECTRICITY_FACTOR),
    }

    status = (
        EmissionStatus.FLAGGED
        if flags else EmissionStatus.PENDING
    )

    return row_model(
        tenant_id=log.tenant_id,
        ingestion_log_id=log.id,
        source_type=SourceType.UTILITY_ELECTRICITY,
        scope=EmissionScope.SCOPE_2,
        description=description,
        source_reference=source_reference,
        raw_source_data=raw,
        normalized_data=normalized,
        activity_value=activity_value,
        activity_unit="kWh",
        emission_factor=ELECTRICITY_FACTOR,
        emission_factor_unit=ELECTRICITY_FACTOR_UNIT,
        co2e_mt=co2e_mt,
        period_start=period_start,
        period_end=period_end,
        status=status,
        flag_reason="; ".join(flags) if flags else None,
    )


# ── Parser: Corporate Travel ──────────────────────────────────────────────────

def parse_travel_row(row, log, row_model):
    """
    Maps a Concur/Navan travel CSV row to a NormalizedEmissionRow (Scope 3).

    Handles three expense categories with separate emission factor logic:

    FLIGHT   — DISTANCE_MILES × cabin-adjusted aviation factor (primary)
               NET_COST × spend-based factor (fallback)
               IATA-only rows (no distance, no cost) → FLAGGED with explanation

    HOTEL    — NIGHTS × 0.0000617 MTCO2e/room-night (DEFRA 2024)
               NET_COST × spend-based factor (fallback when NIGHTS absent)

    GROUND   — Car Rental / Taxi / Train / Bus / Ferry
               DISTANCE_MILES × category-specific factor (primary)
               NET_COST × spend-based factor (fallback)
    """
    from .models import EmissionStatus, EmissionScope, SourceType

    raw          = dict(row)
    flags        = []
    expense_type = str(raw.get("EXPENSE_TYPE", "Flight")).strip()
    expense_key  = expense_type.lower()

    trip_id          = str(raw.get("TRIP_ID", "")).strip()
    origin           = str(raw.get("ORIGIN", "")).strip()
    destination      = str(raw.get("DESTINATION", "")).strip()
    source_reference = trip_id
    description      = (
        f"{expense_type}: {origin}→{destination}"
        if origin and destination else expense_type
    )

    activity_value = co2e_mt = None
    used_factor    = Decimal("0")
    used_unit      = ""
    activity_unit  = "miles"
    calc_method    = "unknown"
    normalized     = {"expense_type": expense_type}

    # ── Hotel ─────────────────────────────────────────────────────────────────
    if expense_key in ("hotel", "accommodation", "lodging"):
        nights_raw = str(raw.get("NIGHTS", "")).strip()
        nights = None
        if nights_raw:
            n, err = _safe_decimal(nights_raw, "NIGHTS")
            if err:
                flags.append(err)
            elif n > 0:
                nights = n

        net_cost_raw = str(raw.get("NET_COST", "")).strip()
        net_cost = None
        if net_cost_raw:
            c, _ = _safe_decimal(net_cost_raw, "NET_COST")
            if c is not None and c > 0:
                net_cost = c

        if nights is not None:
            activity_value = nights.quantize(Decimal("0.0001"))
            co2e_mt        = (activity_value * HOTEL_FACTOR).quantize(Decimal("0.000001"))
            used_factor    = HOTEL_FACTOR
            used_unit      = HOTEL_FACTOR_UNIT
            activity_unit  = "room-nights"
            calc_method    = "room_nights"
            normalized.update({"nights": float(nights), "factor": float(HOTEL_FACTOR)})
        elif net_cost is not None:
            activity_value = net_cost.quantize(Decimal("0.0001"))
            co2e_mt        = (activity_value * SPEND_FACTOR).quantize(Decimal("0.000001"))
            used_factor    = SPEND_FACTOR
            used_unit      = SPEND_FACTOR_UNIT
            activity_unit  = "USD"
            calc_method    = "spend_fallback"
            flags.append("NIGHTS missing — hotel emissions estimated from NET_COST using spend-based factor ($0.0008 MTCO2e/USD)")
            normalized.update({"net_cost_usd": float(net_cost)})
        else:
            flags.append("Hotel row missing both NIGHTS and NET_COST — cannot calculate emissions")

    # ── Ground transport ──────────────────────────────────────────────────────
    elif expense_key in GROUND_FACTORS:
        ground_factor, ground_unit = GROUND_FACTORS[expense_key]

        distance_raw   = str(raw.get("DISTANCE_MILES", "")).strip()
        distance_miles = None
        if distance_raw:
            d, err = _safe_decimal(distance_raw, "DISTANCE_MILES")
            if err:
                flags.append(err)
            elif d > 0:
                distance_miles = d

        net_cost_raw = str(raw.get("NET_COST", "")).strip()
        net_cost = None
        if net_cost_raw:
            c, _ = _safe_decimal(net_cost_raw, "NET_COST")
            if c is not None and c > 0:
                net_cost = c

        if distance_miles is not None:
            activity_value = distance_miles.quantize(Decimal("0.0001"))
            co2e_mt        = (activity_value * ground_factor).quantize(Decimal("0.000001"))
            used_factor    = ground_factor
            used_unit      = ground_unit
            activity_unit  = "miles"
            calc_method    = "distance"
            normalized.update({"distance_miles": float(distance_miles), "factor": float(ground_factor)})
        elif net_cost is not None:
            activity_value = net_cost.quantize(Decimal("0.0001"))
            co2e_mt        = (activity_value * SPEND_FACTOR).quantize(Decimal("0.000001"))
            used_factor    = SPEND_FACTOR
            used_unit      = SPEND_FACTOR_UNIT
            activity_unit  = "USD"
            calc_method    = "spend_fallback"
            flags.append(f"{expense_type}: DISTANCE_MILES missing — estimated from NET_COST ($0.0008 MTCO2e/USD)")
            normalized.update({"net_cost_usd": float(net_cost)})
        else:
            flags.append(f"{expense_type}: missing both DISTANCE_MILES and NET_COST — cannot calculate emissions")

    # ── Flight (default) ──────────────────────────────────────────────────────
    else:
        cabin_raw        = str(raw.get("CABIN_CLASS", "Economy")).strip().lower()
        cabin_multiplier = CABIN_MULTIPLIERS.get(cabin_raw, Decimal("1.0"))
        effective_factor = FLIGHT_BASE_FACTOR * cabin_multiplier

        distance_raw   = str(raw.get("DISTANCE_MILES", "")).strip()
        distance_miles = None

        # Detect bare IATA codes (3-letter alpha) with no distance provided
        iata_only = (
            len(origin) == 3 and origin.isalpha() and
            len(destination) == 3 and destination.isalpha() and
            not distance_raw
        )

        if distance_raw:
            d, err = _safe_decimal(distance_raw, "DISTANCE_MILES")
            if err:
                flags.append(err)
            elif d > 0:
                distance_miles = d

        net_cost_raw = str(raw.get("NET_COST", "")).strip()
        net_cost = None
        if net_cost_raw:
            c, _ = _safe_decimal(net_cost_raw, "NET_COST")
            if c is not None and c > 0:
                net_cost = c

        used_factor   = effective_factor
        used_unit     = FLIGHT_FACTOR_UNIT
        calc_method   = "distance"
        activity_unit = "miles"

        if distance_miles is not None:
            activity_value = distance_miles.quantize(Decimal("0.0001"))
            if activity_value > FLAG_THRESHOLDS["CORPORATE_TRAVEL"]:
                flags.append(f"Unusually high travel distance: {activity_value} miles")
            co2e_mt = (activity_value * effective_factor).quantize(Decimal("0.000001"))
        elif net_cost is not None:
            activity_value = net_cost.quantize(Decimal("0.0001"))
            used_factor    = SPEND_FACTOR
            used_unit      = SPEND_FACTOR_UNIT
            activity_unit  = "USD"
            co2e_mt        = (activity_value * SPEND_FACTOR).quantize(Decimal("0.000001"))
            calc_method    = "spend_fallback"
            if iata_only:
                flags.append(
                    f"Only IATA codes provided ({origin}→{destination}), no distance — "
                    "emissions estimated from NET_COST ($0.0008 MTCO2e/USD)"
                )
            else:
                flags.append("DISTANCE_MILES missing — emissions estimated from NET_COST ($0.0008 MTCO2e/USD)")
        else:
            if iata_only:
                flags.append(
                    f"Only IATA codes provided ({origin}→{destination}) — "
                    "no distance or cost available to calculate emissions"
                )
            else:
                flags.append("Missing both DISTANCE_MILES and NET_COST — cannot calculate emissions")

        normalized.update({
            "distance_miles":     float(distance_miles) if distance_miles else None,
            "cabin_class":        raw.get("CABIN_CLASS", "Economy"),
            "cabin_multiplier":   float(cabin_multiplier),
            "net_cost_usd":       float(net_cost) if net_cost else None,
            "calculation_method": calc_method,
        })

    status = EmissionStatus.FLAGGED if flags else EmissionStatus.PENDING

    return row_model(
        tenant_id=log.tenant_id,
        ingestion_log_id=log.id,
        source_type=SourceType.CORPORATE_TRAVEL,
        scope=EmissionScope.SCOPE_3,
        description=description,
        source_reference=source_reference,
        raw_source_data=raw,
        normalized_data=normalized,
        activity_value=activity_value,
        activity_unit=activity_unit,
        emission_factor=used_factor,
        emission_factor_unit=used_unit,
        co2e_mt=co2e_mt,
        status=status,
        flag_reason="; ".join(flags) if flags else None,
    )


# ── Orchestrator ──────────────────────────────────────────────────────────────

PARSER_MAP = {
    "SAP_FUEL":            parse_sap_row,
    "UTILITY_ELECTRICITY": parse_utility_row,
    "CORPORATE_TRAVEL":    parse_travel_row,
}

# Canonical fields expected by each source parser.
SOURCE_FIELDS = {
    "SAP_FUEL": ["DOC_DATE", "PLANT_CODE", "MATERIAL_ID", "QUANTITY", "UNIT", "AMOUNT", "DESCRIPTION"],
    "CORPORATE_TRAVEL": ["TRIP_ID", "EMPLOYEE_ID", "EXPENSE_TYPE", "ORIGIN", "DESTINATION", "CABIN_CLASS", "DISTANCE_MILES", "NET_COST", "NIGHTS"],
    "UTILITY_ELECTRICITY": ["METER_ID", "SERVICE_START", "SERVICE_END", "USAGE_KWH", "TARIF_CODE", "TOTAL_CHG"],
}

# Fields that must be mapped before a file can be submitted.
# All other SOURCE_FIELDS entries are optional — if unmapped they are omitted
# from the canonical row and the parser falls back to its default/empty behaviour.
REQUIRED_FIELDS = {
    "SAP_FUEL":            ["MATERIAL_ID", "QUANTITY", "UNIT"],
    "CORPORATE_TRAVEL":    ["DISTANCE_MILES", "NET_COST"],
    "UTILITY_ELECTRICITY": ["USAGE_KWH"],
}


def _normalize_column_mapping(column_mapping):
    if not column_mapping:
        return {}
    normalized = {}
    for canonical, source_header in column_mapping.items():
        canonical_key = str(canonical).strip().upper()
        source_key = str(source_header).strip() if source_header is not None else ""
        normalized[canonical_key] = source_key
    return normalized


def _validate_column_mapping(source_type, fieldnames, column_mapping):
    all_fields      = SOURCE_FIELDS.get(source_type, [])
    required_fields = REQUIRED_FIELDS.get(source_type, [])
    mapping         = _normalize_column_mapping(column_mapping)

    if not mapping:
        # No mapping provided — assume headers match canonical names directly
        return {field: field for field in all_fields}

    # Only required fields must be present
    missing = [f for f in required_fields if not mapping.get(f)]
    if missing:
        raise ValueError(
            "Missing column mapping for: " + ", ".join(missing)
        )

    available_headers = {str(name).strip() for name in (fieldnames or []) if name}
    # Validate that every mapped header actually exists in the CSV
    for field in all_fields:
        header = mapping.get(field)
        if header and header not in available_headers:
            raise ValueError(
                f"Mapped header '{header}' not found in CSV columns"
            )

    # Return only fields that were actually mapped (required always, optional if provided)
    return {field: mapping[field] for field in all_fields if mapping.get(field)}


def _map_row_to_canonical(cleaned_row, validated_mapping):
    canonical_row = {}
    for canonical_field, source_header in validated_mapping.items():
        canonical_row[canonical_field] = cleaned_row.get(source_header, "")
    return canonical_row


def process_csv(file_obj, source_type, log, row_model, column_mapping=None):
    """
    Read a CSV file, parse every row through the appropriate parser,
    bulk-create rows using row_model, and update the IngestionLog.

    Returns a summary dict: {rows_created, flagged_rows, approved_rows}
    """
    from .models import EmissionStatus, IngestionStatus

    parser = PARSER_MAP.get(source_type)
    if not parser:
        log.status = IngestionStatus.FAILED
        log.save()
        raise ValueError(f"Unknown source_type: {source_type}")

    try:
        content = file_obj.read()
        if isinstance(content, bytes):
            content = content.decode("utf-8-sig")   # strip BOM from Windows exports

        reader       = csv.DictReader(io.StringIO(content))
        rows_to_save = []

        validated_mapping = _validate_column_mapping(
            source_type,
            reader.fieldnames,
            column_mapping,
        )

        for raw_row in reader:
            # Strip whitespace from every key and value
            cleaned = {k.strip(): (v.strip() if isinstance(v, str) else "") for k, v in raw_row.items() if k}
            canonical = _map_row_to_canonical(cleaned, validated_mapping)
            rows_to_save.append(parser(canonical, log, row_model))

        row_model.objects.bulk_create(rows_to_save)

        flagged_count = sum(
            1 for r in rows_to_save
            if r.status == EmissionStatus.FLAGGED
        )

        log.row_count = len(rows_to_save)
        log.status    = IngestionStatus.COMPLETE
        log.save()

        return {
            "rows_created":  len(rows_to_save),
            "flagged_rows":  flagged_count,
            "approved_rows": 0,
        }

    except Exception:
        log.status = IngestionStatus.FAILED
        log.save()
        raise
