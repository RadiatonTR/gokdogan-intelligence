# Data Sources and API Guide

Gökdoğan Intelligence does not alter a provider's access model. Public sources are used directly where permitted; providers that require credentials use keys supplied by the user.

## Key-management principles

- API keys are not embedded in source code.
- `.env` files or credential files must not be committed to GitHub.
- The application stores supported keys in its local runtime layer and applies them to the running backend.
- **API SİSTEMİNİ TEST ET** verifies status without displaying the key value back to the user.
- Gökdoğan cannot bypass an invalid key, paid-plan requirement, quota or provider access restriction.

## Provider matrix

| Provider / family | Purpose | Credential status |
|---|---|---|
| adsb.lol | ADS-B aircraft observations | Generally public access; provider terms apply |
| OpenSky Network | Aircraft enrichment / authenticated access | Account/authentication may be useful or required for some features |
| Airframes.io | ACARS/VDL/airframe enrichment | API key required |
| AISStream | Live AIS stream | API key required |
| Global Fishing Watch | Maritime/fishing activity enrichment | Token may be required depending on feature/endpoint |
| Sentinel Hub / Copernicus | Optical/SAR imagery workflows | Relevant account/client credentials required |
| TomTom | Traffic flow/incidents | API key required |
| Shodan | Authorized Internet-asset search | API key required |
| Finnhub | Market enrichment | Optional API key |
| Open-Meteo | Weather and selected environmental data | Public endpoints may be keyless |
| RainViewer | Radar | Current provider terms apply |
| NASA/USGS/NOAA | Disaster/satellite/space-weather data | Mostly public services; endpoint terms apply |

## Public camera / CCTV sources

Gökdoğan source code and release packages must not contain private-camera credentials. The supported model is limited to:

- public traffic-camera APIs,
- open catalogs published by municipalities/transport authorities,
- official URL lists added by an authorized operator.

If a source requires a password, VPN or closed network, only an authorized user may configure access in their own environment. Gökdoğan does not bypass access controls.

## Current notes for public camera providers

- **Singapore LTA DataMall:** Dynamic APIs use an Account Key issued to registered users. LTA announced that after 30 June 2026 traffic-camera coverage is limited to Woodlands/Tuas checkpoints, selected AYE/BKE approaches and Sentosa Gateway. A smaller camera count therefore does not necessarily indicate a Gökdoğan fault.
- **Ontario 511:** The official `GET Cameras` API can provide camera ID, road, direction, latitude/longitude and related fields.
- **ASFINAG:** Its traffic-data portal provides public webcam data as part of traffic-information services. Public webcams are not the same as access-controlled operational cameras.

Current provider terms and API documentation take precedence over application-side assumptions.

## Missing fields in aviation and maritime data

ADS-B/AIS broadcasts do not provide every possible field. Normal conditions include:

- unknown departure/arrival,
- unknown route,
- unknown aircraft/vessel type,
- unknown operator,
- a short observed track,
- an old last message.

Configured enrichment providers may fill some of these fields.

## Source freshness

Each provider has a different update interval. Interpret the UI's freshness/live indicator according to the last successful update from that source.

## Attribution references

See [`../../DATA-ATTRIBUTION.md`](../../DATA-ATTRIBUTION.md) for the detailed provider, license and attribution list.
