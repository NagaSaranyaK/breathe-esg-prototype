# Data Sources and Field Provenance

For each of the three source systems, this document explains:
- What real-world format we researched
- What we learned about the data
- What our sample CSVs look like and why
- What would break in a real deployment

---

## 1. SAP Fuel & Procurement (Scope 1)

### What real-world format we researched

SAP is the most common ERP system in large enterprises. Fuel purchase data lives in the Materials Management (MM) module. Companies export it via SAP transactions like SE16 or custom ABAP reports — the output is typically a flat CSV with columns like document date, plant code, material number, quantity, and unit.

### What we learned

- The **material number** (e.g. `DIESEL_04`) tells you what fuel was bought. We use the description or prefix to identify the fuel type (diesel, petrol, LPG).
- **Quantity + Unit** is the activity data. We multiply litres × fuel-specific emission factor to get CO₂e.
- Different companies name the same columns differently — one might call it `DOC_DATE`, another `Transaction_Date`, another `posting_date`.
- Some exports include zero-quantity rows (cancelled orders, reversals). These need to be flagged, not calculated.

### What our sample data looks like

```csv
DOC_DATE,PLANT_CODE,MATERIAL_ID,QUANTITY,UNIT,AMOUNT,DESCRIPTION
2026-01-05,US01,DIESEL_04,1500,L,1850.00,Low-Sulfur Diesel
2026-01-19,US02,PETROL_01,980,L,1274.00,Unleaded Petrol
2026-02-02,US02,DIESEL_04,0,L,0.00,Low-Sulfur Diesel    ← zero qty, gets flagged
```

We created 4 sets with different column naming styles (canonical, SAP European, Oracle/Concur, generic spreadsheet) to test that the field-mapping UI works regardless of header names.

### What would break in a real deployment

| Problem | Why it's hard |
|---------|---------------|
| Unit conversion | Real SAP exports use dozens of UoM codes (`GAL`, `KL`, `M3`, `BBL`). We only handle `L`/`LTR`. |
| Material master lookup | The material number alone isn't enough — you need SAP's material master table to reliably identify fuel type. Our prefix-matching is fragile. |
| Multi-currency | `AMOUNT` could be in any currency. We ignore it for calculation but a real system would need FX conversion for spend-based fallbacks. |
| Negative quantities | Stock returns show as negative. We flag zeros but don't handle negative reversal logic. |

---

## 2. Utility Electricity (Scope 2)

### What real-world format we researched

Electricity data comes from utility portals (PG&E, National Grid, Con Edison) or energy management platforms (Arcadia, Urjanet). Most allow CSV download of billing history with fields like meter ID, service period, kWh consumed, and charges.

### What we learned

- The key field is **USAGE_KWH** — that's the activity data. We multiply it by the grid emission factor to get CO₂e.
- **Service dates** (start/end) are critical — they tell you *when* the electricity was actually consumed, not when the bill was issued. ESG standards require emissions to be assigned to the consumption period.
- Meter IDs identify specific facilities/sites — useful for location-based reporting.
- Tariff codes and charges are financial data that don't affect the emission calculation.

### What our sample data looks like

```csv
METER_ID,SERVICE_START,SERVICE_END,USAGE_KWH,TARIF_CODE,TOTAL_CHG
MET-88402-X,2026-04-12,2026-05-11,42500,COMM_E1,5100.00
MET-88405-C,2026-04-20,2026-05-19,0,RES_E1,0.00    ← zero usage, gets flagged
```

We included rows with zero kWh (vacant premises or meter errors) to test the flagging logic.

### What would break in a real deployment

| Problem | Why it's hard |
|---------|---------------|
| Regional grid factors | We use one US national average (0.000386). In reality, California's grid is 3× cleaner than the Southeast. Real systems need eGRID subregion factors per meter location. |
| Renewable energy credits (RECs) | If a tenant buys green energy, their Scope 2 should be lower. We don't handle market-based vs. location-based accounting. |
| Non-US facilities | Outside the US, you need IEA country-specific factors. We only have the EPA number. |
| Overlapping bills | Some utilities issue overlapping service periods. We don't de-duplicate or detect double-counting. |
| Unit variations | Some utilities report in MWh, therms, or GJ instead of kWh. We only handle kWh. |

---

## 3. Corporate Travel (Scope 3)

### What real-world format we researched

Travel data comes from expense management systems like SAP Concur, Navan (TripActions), or Egencia. These export trip-level CSVs with fields like trip ID, expense type, origin/destination, distance, cabin class, cost, and nights.

### What we learned

- **Expense type** determines which calculation branch to use: Flight, Hotel, or Ground Transport.
- For **flights**: distance × cabin-adjusted factor. Business class emits ~2.9× more per mile than economy (larger seat = more floor space = more fuel attributed to that passenger).
- For **hotels**: room-nights × average hotel factor. Property-level data isn't available in standard expense exports.
- For **ground transport**: distance × mode-specific factor (car, taxi, train, bus, ferry).
- When distance is missing but cost is present, we use a spend-based fallback and flag the row.
- Airport codes (3-letter IATA like `JFK`, `LHR`) often appear without distance — we flag these rather than auto-calculating geodesic distance.

### What our sample data looks like

```csv
TRIP_ID,EMPLOYEE_ID,EXPENSE_TYPE,ORIGIN,DESTINATION,CABIN_CLASS,DISTANCE_MILES,NET_COST,NIGHTS
T-9901,EMP-401,Flight,JFK,LHR,Business,3450,1200.00,
T-9910,EMP-812,Hotel,NYC,NYC,,,,3          ← hotel: uses NIGHTS
T-9915,EMP-234,Car Rental,,,,,185,95.00,    ← ground: uses distance
T-9918,EMP-103,Flight,BOM,DEL,Economy,,50.00, ← no distance, spend fallback + flag
```

All travel CSVs include a mix of flights, hotels, and ground rows so every normalisation path gets exercised.

### What would break in a real deployment

| Problem | Why it's hard |
|---------|---------------|
| Multi-leg flights | A trip SFO→DEN→JFK might appear as one row or two. We treat each row independently — no itinerary grouping. |
| Shared rides / pooling | If 3 colleagues share a taxi, the emission should be split. We can't detect shared trips from expense data. |
| Hotel property factors | A luxury resort emits more than a budget hotel. Without property-level data, our global average is imprecise. |
| Non-mile distances | Some systems report in km. We assume miles everywhere. |
| Personal vs. business travel | Expense reports might include personal legs of a blended trip. We can't distinguish them. |
| Cabin class variations | Systems report class differently (`Y`, `J`, `F`, `W`, `Econ`, `Biz`). We only match full English names. |

---

## Emission factor references

| Factor | Value | Source document |
|--------|-------|-----------------|
| Diesel | 0.002701 MTCO₂e/L | IPCC AR6 (2.68 kgCO₂e/L converted) |
| Petrol / gasoline | 0.002289 MTCO₂e/L | IPCC AR6 (2.31 kgCO₂e/L) |
| LPG | 0.001542 MTCO₂e/L | IPCC AR6 (1.61 kgCO₂e/L) |
| Electricity | 0.000386 MTCO₂e/kWh | US EPA eGRID 2024 national average |
| Aviation (economy) | 0.000255 MTCO₂e/mile | DEFRA 2024, Section 6 — Business Travel Air |
| Hotel | 0.0000617 MTCO₂e/room-night | DEFRA 2024, Section 7 — Hotel Stay |
| Car rental | 0.000168 MTCO₂e/mile | DEFRA 2024, Section 6 — Land Travel |
| Taxi / rideshare | 0.000211 MTCO₂e/mile | DEFRA 2024, Section 6 |
| Train / rail | 0.0000041 MTCO₂e/mile | DEFRA 2024, Section 6 |
| Bus | 0.0000089 MTCO₂e/mile | DEFRA 2024, Section 6 |
| Ferry | 0.000113 MTCO₂e/mile | DEFRA 2024, Section 6 |
| Spend-based fallback | 0.0008 MTCO₂e/USD | Industry average (always flagged for review) |

**Reference links:**
- DEFRA 2024 Conversion Factors: https://www.gov.uk/government/publications/greenhouse-gas-reporting-conversion-factors-2024
- US EPA eGRID: https://www.epa.gov/egrid
- IPCC AR6 WG3: https://www.ipcc.ch/report/ar6/wg3/
