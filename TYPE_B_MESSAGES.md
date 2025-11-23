# Type-B Message Support

This implementation adds IATA Type-B message generation to the baggage handling simulator, emitting operational messages at key flight lifecycle milestones.

## Overview

Type-B messages are standard teletype messages used in the aviation industry for communicating operational information between airlines, airports, and ground handlers. This simulator now generates CloudEvents containing both structured data and raw Type-B message formats.

## Implemented Message Types

### 1. LDM (Load Message)
**Emitted:** After check-in closes (flight_closed event)

**Purpose:** Provides final load information including passenger and baggage counts before departure.

**Event Type:** `Airport.Flight.TypeB.LDM`

**Sample Raw Message:**
```
LDM
NV4399/23NOV.FRAMUC
.PAX 98
.BAG 69 T1242K
.TOTAL BAGS 69
```

**Structured Data:**
```json
{
  "flightId": "...",
  "flightNumber": "NV4399",
  "airline": "NV",
  "origin": "FRA",
  "destination": "MUC",
  "departureUtc": "2025-11-23T20:54:00Z",
  "messageType": "LDM",
  "rawMessage": "LDM\nNV4399/23NOV.FRAMUC\n...",
  "loadData": {
    "passengers": 98,
    "bags": 69,
    "totalWeightKg": 1242.3
  }
}
```

### 2. MVT/DEP (Movement Departure)
**Emitted:** At actual departure time (flight_departed event)

**Purpose:** Reports actual aircraft off-block/departure time.

**Event Type:** `Airport.Flight.TypeB.MVT.DEP`

**Sample Raw Message:**
```
MVT
NV4399/23NOV.FRAMUC
DEP 2054
AC A220
```

**Structured Data:**
```json
{
  "flightId": "...",
  "flightNumber": "NV4399",
  "airline": "NV",
  "origin": "FRA",
  "destination": "MUC",
  "aircraft": "A220",
  "messageType": "MVT/DEP",
  "rawMessage": "MVT\nNV4399/23NOV.FRAMUC\n...",
  "movementData": {
    "movementType": "departure",
    "actualTimeUtc": "2025-11-23T20:54:00Z",
    "scheduledTimeUtc": "2025-11-23T20:54:00Z"
  }
}
```

### 3. MVT/ARR (Movement Arrival)
**Emitted:** At actual arrival time (flight_arrived event)

**Purpose:** Reports actual aircraft on-block/arrival time at destination.

**Event Type:** `Airport.Flight.TypeB.MVT.ARR`

**Sample Raw Message:**
```
MVT
NV4399/23NOV.FRAMUC
ARR 2154
AC A220
```

**Structured Data:**
```json
{
  "flightId": "...",
  "flightNumber": "NV4399",
  "aircraft": "A220",
  "messageType": "MVT/ARR",
  "rawMessage": "MVT\nNV4399/23NOV.FRAMUC\n...",
  "movementData": {
    "movementType": "arrival",
    "actualTimeUtc": "2025-11-23T21:54:00Z",
    "scheduledTimeUtc": "2025-11-23T21:54:00Z"
  }
}
```

## Event Flow Sequence

```
Flight Scheduled
    ↓
Check-in Opens
    ↓
Passengers & Baggage Check-in
    ↓
Check-in Closes → **LDM emitted**
    ↓
Baggage Loading
    ↓
Departure → **MVT/DEP emitted**
    ↓
In Flight
    ↓
Arrival → **MVT/ARR emitted**
    ↓
Baggage Unloading & Delivery
```

## Implementation Details

### Helper Methods

- `_generate_type_b_ldm()` - Formats LDM message in IATA Type-B format
- `_generate_type_b_mvt()` - Formats MVT message in IATA Type-B format
- `_emit_type_b_ldm()` - Sends LDM CloudEvent
- `_emit_type_b_mvt_dep()` - Sends MVT departure CloudEvent
- `_emit_type_b_mvt_arr()` - Sends MVT arrival CloudEvent

### Integration Points

Messages are emitted at specific points in the flight lifecycle within `_tick_flights()`:

1. **After flight_closed** - LDM message sent with final passenger/baggage counts
2. **After flight_departed** - MVT/DEP message sent with actual departure time
3. **After flight_arrived** - MVT/ARR message sent with actual arrival time

### Console Output

Type-B messages are displayed with a 📄 emoji in verbose console output for easy identification.

## Usage

Type-B messages are automatically emitted during normal simulator operation:

```bash
# Dry-run with verbose output to see Type-B messages
python -m baggage_simulator.cli --dry-run --verbose --clock-speed 120

# Live run with Event Hubs (Type-B messages sent as CloudEvents)
python -m baggage_simulator.cli \
  --clock-speed 120 \
  --eventhub-conn $EVENTHUB_CONNECTION_STRING \
  --eventhub-name $EVENTHUB_NAME \
  --sql-conn $SQLSERVER_CONNECTION_STRING
```

## CloudEvents Format

All Type-B messages are sent as CloudEvents with:
- **specversion:** 1.0
- **type:** `Airport.Flight.TypeB.{LDM|MVT.DEP|MVT.ARR}`
- **source:** Airport code (origin for LDM/MVT.DEP, destination for MVT.ARR)
- **subject:** `flight/{flightNumber}`
- **datacontenttype:** application/json

The `data` payload contains both:
- **rawMessage:** The IATA Type-B formatted message text
- **Structured fields:** Parsed operational data (loadData, movementData)

## Notes

- Message formats follow simplified IATA Type-B standards
- Actual production systems may require additional message fields
- Times are in UTC and formatted as HHMM in raw messages
- All structured data provides full ISO 8601 timestamps
- Messages are batched with same-flight events for efficient Event Hubs transmission

## Future Extensions

Potential additional Type-B messages:
- **CPM** (Passenger Manifest) - Detailed passenger list
- **UCM** (Container Messages) - ULD/container information
- **PSM** (Passenger Seat Messages) - Seating assignments
- **BTM** (Baggage Transfer Messages) - Connecting bag information
