from decimal import Decimal

from django.test import SimpleTestCase

from .normalization import (
	_map_row_to_canonical,
	_validate_column_mapping,
	parse_sap_row,
	parse_travel_row,
	parse_utility_row,
)


class _DummyLog:
	def __init__(self, tenant_id=101, row_id=555):
		self.tenant_id = tenant_id
		self.id = row_id


class _RowFactory:
	def __call__(self, **kwargs):
		return kwargs


class ColumnMappingTests(SimpleTestCase):
	def test_validate_mapping_uses_identity_when_mapping_not_provided(self):
		mapping = _validate_column_mapping(
			"UTILITY_ELECTRICITY",
			["METER_ID", "SERVICE_START", "SERVICE_END", "USAGE_KWH", "TARIF_CODE", "TOTAL_CHG"],
			None,
		)
		self.assertEqual(mapping["METER_ID"], "METER_ID")
		self.assertEqual(mapping["USAGE_KWH"], "USAGE_KWH")

	def test_validate_mapping_rejects_missing_required_field(self):
		with self.assertRaises(ValueError) as err:
			_validate_column_mapping(
				"SAP_FUEL",
				["posting_date", "company_code", "qty", "uom", "amount", "desc"],
				{
					"DOC_DATE":     "posting_date",
					"PLANT_CODE":   "company_code",
					# MATERIAL_ID intentionally missing (required field)
					"QUANTITY":     "qty",
					"UNIT":         "uom",
					"AMOUNT":       "amount",
					"DESCRIPTION":  "desc",
				},
			)
		self.assertIn("Missing column mapping", str(err.exception))

	def test_map_row_to_canonical_translates_custom_headers(self):
		mapping = {
			"DOC_DATE": "posting_date",
			"PLANT_CODE": "company_code",
			"MATERIAL_ID": "material",
			"QUANTITY": "qty",
			"UNIT": "uom",
			"AMOUNT": "amount",
			"DESCRIPTION": "desc",
		}
		row = {
			"posting_date": "2026-05-01",
			"company_code": "ACME01",
			"material": "DIESEL-123",
			"qty": "1500",
			"uom": "L",
			"amount": "4300",
			"desc": "Diesel purchase",
		}
		canonical = _map_row_to_canonical(row, mapping)
		self.assertEqual(canonical["DOC_DATE"], "2026-05-01")
		self.assertEqual(canonical["QUANTITY"], "1500")
		self.assertEqual(canonical["DESCRIPTION"], "Diesel purchase")


class ParserBehaviorTests(SimpleTestCase):
	def setUp(self):
		self.log = _DummyLog()
		self.row_factory = _RowFactory()

	def test_parse_sap_row_populates_scope_and_ids(self):
		row = {
			"DOC_DATE": "2026-05-01",
			"PLANT_CODE": "ACME01",
			"MATERIAL_ID": "DIESEL-XYZ",
			"QUANTITY": "100",
			"UNIT": "L",
			"AMOUNT": "250",
			"DESCRIPTION": "Diesel",
		}
		parsed = parse_sap_row(row, self.log, self.row_factory)

		self.assertEqual(parsed["tenant_id"], 101)
		self.assertEqual(parsed["ingestion_log_id"], 555)
		self.assertEqual(parsed["activity_unit"], "L")
		self.assertEqual(parsed["source_reference"], "2026-05-01-ACME01-DIESEL-XYZ")
		self.assertGreater(parsed["co2e_mt"], Decimal("0"))

	def test_parse_utility_row_flags_zero_usage(self):
		row = {
			"METER_ID": "MET-001",
			"SERVICE_START": "2026-05-01",
			"SERVICE_END": "2026-05-31",
			"USAGE_KWH": "0",
			"TARIF_CODE": "COMM_E1",
			"TOTAL_CHG": "0",
		}
		parsed = parse_utility_row(row, self.log, self.row_factory)
		self.assertEqual(parsed["status"], "FLAGGED")
		self.assertIn("Zero or negative electricity usage", parsed["flag_reason"])

	def test_parse_travel_row_uses_spend_fallback_when_distance_missing(self):
		row = {
			"TRIP_ID": "T-100",
			"EMPLOYEE_ID": "E-9",
			"EXPENSE_TYPE": "Flight",
			"ORIGIN": "Hyderabad",
			"DESTINATION": "New Delhi",
			"CABIN_CLASS": "Economy",
			"DISTANCE_MILES": "",
			"NET_COST": "1200",
			"NIGHTS": "",
		}
		parsed = parse_travel_row(row, self.log, self.row_factory)

		self.assertEqual(parsed["activity_unit"], "USD")
		self.assertEqual(parsed["emission_factor_unit"], "MTCO2e/USD")
		self.assertEqual(parsed["normalized_data"]["calculation_method"], "spend_fallback")
		self.assertIn("DISTANCE_MILES missing", parsed["flag_reason"])


class TravelHotelParserTests(SimpleTestCase):
	def setUp(self):
		self.log = _DummyLog()
		self.rf  = _RowFactory()

	def _row(self, **overrides):
		base = {
			"TRIP_ID": "T-200", "EMPLOYEE_ID": "E-5",
			"EXPENSE_TYPE": "Hotel", "ORIGIN": "LHR", "DESTINATION": "LHR",
			"CABIN_CLASS": "", "DISTANCE_MILES": "", "NET_COST": "", "NIGHTS": "",
		}
		base.update(overrides)
		return base

	def test_hotel_with_nights_uses_hotel_factor(self):
		parsed = parse_travel_row(self._row(NIGHTS="3"), self.log, self.rf)
		self.assertEqual(parsed["activity_unit"], "room-nights")
		self.assertEqual(parsed["emission_factor_unit"], "MTCO2e/room-night")
		self.assertEqual(parsed["activity_value"], Decimal("3.0000"))
		# 3 × 0.0000617 = 0.0001851
		self.assertEqual(parsed["co2e_mt"], Decimal("0.000185"))
		self.assertEqual(parsed["status"], "PENDING")

	def test_hotel_spend_fallback_when_nights_missing(self):
		parsed = parse_travel_row(self._row(NET_COST="500"), self.log, self.rf)
		self.assertEqual(parsed["activity_unit"], "USD")
		self.assertEqual(parsed["emission_factor_unit"], "MTCO2e/USD")
		self.assertEqual(parsed["status"], "FLAGGED")
		self.assertIn("NIGHTS missing", parsed["flag_reason"])

	def test_hotel_flagged_when_both_nights_and_cost_missing(self):
		parsed = parse_travel_row(self._row(), self.log, self.rf)
		self.assertIsNone(parsed["co2e_mt"])
		self.assertEqual(parsed["status"], "FLAGGED")
		self.assertIn("missing both", parsed["flag_reason"].lower())

	def test_hotel_aliases_recognised(self):
		for expense_type in ("accommodation", "Accommodation", "Lodging", "lodging"):
			with self.subTest(expense_type=expense_type):
				parsed = parse_travel_row(
					self._row(EXPENSE_TYPE=expense_type, NIGHTS="2"),
					self.log, self.rf,
				)
				self.assertEqual(parsed["activity_unit"], "room-nights")


class TravelGroundParserTests(SimpleTestCase):
	def setUp(self):
		self.log = _DummyLog()
		self.rf  = _RowFactory()

	def _row(self, expense_type, distance="", net_cost=""):
		return {
			"TRIP_ID": "T-300", "EMPLOYEE_ID": "E-7",
			"EXPENSE_TYPE": expense_type, "ORIGIN": "", "DESTINATION": "",
			"CABIN_CLASS": "", "DISTANCE_MILES": distance, "NET_COST": net_cost,
			"NIGHTS": "",
		}

	def test_car_rental_with_distance(self):
		parsed = parse_travel_row(self._row("Car Rental", distance="100"), self.log, self.rf)
		self.assertEqual(parsed["activity_unit"], "miles")
		self.assertEqual(parsed["emission_factor_unit"], "MTCO2e/mile")
		# 100 × 0.000168 = 0.0168
		self.assertEqual(parsed["co2e_mt"], Decimal("0.016800"))
		self.assertEqual(parsed["status"], "PENDING")

	def test_train_with_distance(self):
		parsed = parse_travel_row(self._row("Train", distance="200"), self.log, self.rf)
		self.assertEqual(parsed["emission_factor_unit"], "MTCO2e/mile")
		# 200 × 0.0000041 = 0.00082
		self.assertEqual(parsed["co2e_mt"], Decimal("0.000820"))

	def test_taxi_with_distance(self):
		parsed = parse_travel_row(self._row("Taxi", distance="15"), self.log, self.rf)
		# 15 × 0.000211 = 0.003165
		self.assertEqual(parsed["co2e_mt"], Decimal("0.003165"))

	def test_ground_spend_fallback_when_distance_missing(self):
		parsed = parse_travel_row(self._row("Car Rental", net_cost="120"), self.log, self.rf)
		self.assertEqual(parsed["activity_unit"], "USD")
		self.assertEqual(parsed["status"], "FLAGGED")
		self.assertIn("DISTANCE_MILES missing", parsed["flag_reason"])

	def test_ground_all_modes_recognised(self):
		modes = ["car rental", "rental car", "taxi", "rideshare", "train", "rail", "bus", "ferry"]
		for mode in modes:
			with self.subTest(mode=mode):
				parsed = parse_travel_row(self._row(mode, distance="50"), self.log, self.rf)
				self.assertEqual(parsed["activity_unit"], "miles")
				self.assertGreater(parsed["co2e_mt"], Decimal("0"))


class TravelFlightParserTests(SimpleTestCase):
	def setUp(self):
		self.log = _DummyLog()
		self.rf  = _RowFactory()

	def _row(self, **overrides):
		base = {
			"TRIP_ID": "T-400", "EMPLOYEE_ID": "E-3",
			"EXPENSE_TYPE": "Flight", "ORIGIN": "JFK", "DESTINATION": "LHR",
			"CABIN_CLASS": "Economy", "DISTANCE_MILES": "3450",
			"NET_COST": "900", "NIGHTS": "",
		}
		base.update(overrides)
		return base

	def test_flight_economy_uses_base_factor(self):
		parsed = parse_travel_row(self._row(), self.log, self.rf)
		# 3450 × 0.000255 = 0.87975
		self.assertEqual(parsed["co2e_mt"], Decimal("0.879750"))
		self.assertEqual(parsed["status"], "PENDING")

	def test_flight_business_applies_2x_multiplier(self):
		economy = parse_travel_row(self._row(), self.log, self.rf)
		business = parse_travel_row(self._row(CABIN_CLASS="Business"), self.log, self.rf)
		self.assertEqual(business["co2e_mt"], economy["co2e_mt"] * 2)

	def test_flight_first_applies_2_5x_multiplier(self):
		economy = parse_travel_row(self._row(), self.log, self.rf)
		first   = parse_travel_row(self._row(CABIN_CLASS="First"), self.log, self.rf)
		self.assertEqual(first["co2e_mt"], economy["co2e_mt"] * Decimal("2.5"))

	def test_iata_only_row_flagged_with_descriptive_message(self):
		parsed = parse_travel_row(self._row(DISTANCE_MILES="", NET_COST="800"), self.log, self.rf)
		self.assertEqual(parsed["activity_unit"], "USD")
		self.assertIn("IATA codes", parsed["flag_reason"])
		self.assertIn("JFK", parsed["flag_reason"])

	def test_missing_distance_and_cost_produces_null_co2e(self):
		parsed = parse_travel_row(self._row(DISTANCE_MILES="", NET_COST=""), self.log, self.rf)
		self.assertIsNone(parsed["co2e_mt"])
		self.assertEqual(parsed["status"], "FLAGGED")

