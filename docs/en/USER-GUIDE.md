# User Guide

## Main screen

Gökdoğan's main screen consists of four primary areas:

1. **Left Data Layers:** manages data families and counters.
2. **Center Map:** displays geographic events, observed tracks/routes and assets.
3. **Right Operations Panels:** opens news, diplomacy, air/ground traffic, market and filter modules.
4. **Bottom Status Bar:** displays location, map style and selected live-source counters.

## Using the map

- Use the mouse wheel to zoom in and out.
- Select a marker or route to open its detail panel.
- Enable or disable layers from the left panel.
- Switch between supported satellite/standard basemaps.
- Disable unused layers when the map becomes crowded.

## Search

Depending on the configured data sources, search can be used to navigate to:

- place names,
- coordinates,
- callsigns,
- selected asset identifiers.

## Aircraft

When an aircraft is selected, the current data set may provide fields such as:

- callsign
- ICAO/registration
- model
- operator
- altitude
- ground speed
- heading
- first/last observation
- observed track/route
- external reference link

Some fields require a separate provider or API key. `BİLİNMİYOR` (Unknown) does not necessarily indicate an application error; the upstream data source may simply not provide that field.

## Maritime vessels

When AIS data is available, fields may include:

- MMSI/IMO
- vessel name/type
- position
- speed/course
- observed track
- last update

If AISStream is temporarily unavailable, Gökdoğan reports the provider state through source health and can use configured cache/fallback sources where available.

## Public camera sources

The public-camera area is intended for:

- official traffic/city camera catalogs,
- catalog URLs added by an authorized operator,
- public providers that require an API key.

Selecting a camera link may open the provider in the system browser. Unauthorized access to private or closed camera networks is not supported.

## News and diplomacy

News/diplomacy cards may show:

- headline
- source
- time
- location/event context where available
- external source link

Headline language may come directly from the publisher. The v1.0.0 Gökdoğan desktop controls remain Turkish-first.

## Disasters

Enable disaster layers individually to inspect earthquakes, fires, volcanoes and other events. For critical situations, always verify information with the relevant official authority as well.

## Weather

Forecast, radar and air-quality layers may come from different providers. Map time and provider update time may differ.

## Markets

The market bar and Market Center show indicators from configured providers. Data may be delayed and does not constitute investment advice.

## API management

Under **Ayarlar → API Anahtarları**:

1. Enter the provider key.
2. Save it.
3. Run **API SİSTEMİNİ TEST ET**.
4. Confirm that the provider appears as ready/active in the Intelligence Center.

The API key itself should not be displayed back to the user in plaintext after saving.

## Source health

If a layer shows no data, check source status first:

- Is a key missing?
- Is the service offline?
- Has the quota been reached?
- Is the data delayed?
- Is cached data being shown?

This distinction is the fastest way to determine whether the application itself is failing or the upstream source is unavailable.

## Operating profiles

- **DENGELİ (Balanced):** recommended default for stability and provider quotas.
- **MAKSİMUM (Maximum):** uses higher concurrency/map budgets on more capable computers.

The Maximum profile does not bypass third-party API limits.
