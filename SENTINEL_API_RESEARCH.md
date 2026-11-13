# Sentinel-1 GRD API integration brief

ASF is the sole Sentinel-1 source in the current tool. The CDSE material below is retained as research for a possible later integration.

Checked 12 November 2026 against provider and STAC documentation. CDSE asset mapping was validated with a live STAC item on 13 November 2026.

CDSE `sentinel-1-grd` Items expose a `Product` ZIP asset with an HTTPS OData download URL. Its UUID also appears in `properties._private.product_uuid`; the Item ID is a Sentinel product name, not the OData UUID. The collection includes GRD COG Items, identifiable by a `_COG` suffix in the product name. Earth Search's `sentinel-1-grd` Items expose per-polarization COG assets through requester-pays S3 URLs rather than a complete product ZIP.

## Recommendation

Build the **ASF adapter first** using the official `asf_search` Python package. It directly supports SAR filters, pagination through `search_generator()`, Earthdata authentication, and download. Then build **CDSE discovery** against its current STAC endpoint and **CDSE download** through the documented authenticated product/asset URL. Keep provider IDs and source records intact; the same Sentinel-1 acquisition may appear in both catalogues. [ASF search basics](https://docs.asf.alaska.edu/asf_search/basics/), [ASF best practices](https://docs.asf.alaska.edu/asf_search/BestPractices/), [CDSE STAC catalogue](https://documentation.dataspace.copernicus.eu/APIs/STAC.html), [CDSE OData downloads](https://documentation.dataspace.copernicus.eu/APIs/OData.html).

The first implementation should target **Sentinel-1 GRD only**. Do not infer that SLC, bursts, or processed backscatter have identical assets or processing semantics. ASF's broader Sentinel-1 platform search can include derived products, so constrain the product type rather than filtering by platform alone. [ASF best practices](https://docs.asf.alaska.edu/asf_search/BestPractices/).

## Interface comparison

| Concern | ASF | CDSE |
| --- | --- | --- |
| Search interface | `asf_search` `geo_search()` / `search()` with `ASFSearchOptions`; search API is also available over HTTP. | Current product STAC base `https://stac.dataspace.copernicus.eu/v1/`, with `POST /search` and collection `sentinel-1-grd`. Avoid the deprecated legacy STAC URL. |
| Geometry and time | `intersectsWith` WKT, `start`, `end`; filter dataset/platform and `processingLevel`. | STAC `intersects` GeoJSON or `bbox` in longitude/latitude, `datetime` interval, and `collections: ["sentinel-1-grd"]`. |
| SAR filters | `beamMode`, `polarization`, `flightDirection`, `processingLevel`, orbit fields among documented options. | Check `/collections/sentinel-1-grd/queryables`; use supported STAC Filter/CQL2 fields for instrument mode, polarization, orbit state, etc. Do not assume ASF and CDSE field names or value sets are interchangeable. |
| Pagination | `search_generator()` yields result pages; ASF documents a default page size of 250. | Follow the returned STAC `links` entry with `rel: "next"`, respecting its method/body/headers. Do not manufacture page numbers. |
| Result identity and metadata | `ASFProduct.properties`, `geojson()`, `umm`, and `metadata`; `fileID` and `url` are documented properties. | STAC Item `id`, `collection`, `geometry`, `properties`, `assets`, and links. Preserve the full Item as provider metadata. |
| Download | `ASFProduct.download()` or `asf_search.download_url(s)`, normally with Earthdata Login via `.netrc` or `ASFSession` token/credentials. | CDSE product download uses bearer token and a product UUID in `https://download.dataspace.copernicus.eu/odata/v1/Products(<id>)/$value`. Tokens can be refreshed. Inspect STAC asset links and their product identifiers before wiring STAC discovery to OData download. |

Sources: [ASF search options](https://docs.asf.alaska.edu/asf_search/ASFSearchOptions/), [ASF search filters](https://docs.asf.alaska.edu/asf_search/searching/), [ASF paging and product properties](https://docs.asf.alaska.edu/asf_search/BestPractices/), [ASF downloads](https://docs.asf.alaska.edu/asf_search/downloading/), [CDSE STAC](https://documentation.dataspace.copernicus.eu/APIs/STAC.html), [STAC paging examples](https://github.com/radiantearth/stac-api-spec/blob/release/v1.0.0/item-search/examples.md), [CDSE OData](https://documentation.dataspace.copernicus.eu/APIs/OData.html).

## Suggested adapter contract

```python
class ProviderAdapter(Protocol):
    def search(self, query: SearchQuery) -> Iterable[Scene]: ...
    def resolve_download(self, scene: Scene) -> DownloadAsset: ...
    def download(self, asset: DownloadAsset, destination: Path) -> DownloadReceipt: ...
```

`SearchQuery` should contain a WGS84 AOI, UTC interval, product type, optional polarization/mode/orbit filters, and a maximum result count. `Scene` should retain provider-scoped ID, original product name, acquisition interval, geometry, mission/platform, GRD mode/polarizations, source URL, available assets, optional byte size, and full provider metadata. `DownloadReceipt` should capture final path, bytes, checksum if available, and source asset URL. A provider-neutral model should allow missing optional fields rather than inventing values.

The service layer should use stable IDs such as `asf:<fileID>` and `cdse:<STAC item id>`, then group likely duplicate acquisitions by canonical Sentinel product name after verifying naming equivalence. Keep distinct provider entries selectable so users can choose the download source.

## Authentication and limits

- ASF: downloads usually need Earthdata Login; official guidance prefers `.netrc`, with `ASFSession` credentials or token as alternatives. Search API documentation reports HTTP 429 when request rate exceeds 250 per minute. [ASF downloading](https://docs.asf.alaska.edu/asf_search/downloading/), [ASF troubleshooting](https://docs.asf.alaska.edu/api/troubleshooting/).
- CDSE: product downloads require an access token; the documented identity endpoint returns access and refresh tokens. The CDSE quota table currently lists general-user S3/OData/STAC limits, including 2,000 requests per minute, four concurrent immediate-data connections, and a 10-minute access-token lifetime. Make throttling configurable and honor `429` and `Retry-After`; do not hard-code the published ceiling as a target rate. [CDSE OData](https://documentation.dataspace.copernicus.eu/APIs/OData.html), [CDSE quotas](https://documentation.dataspace.copernicus.eu/Quotas.html).
- Credentials belong in `.netrc`, environment variables, or a local credential store. Exclude them from config examples, manifests, logs, and Git.

## First adapter spike and acceptance checks

1. Create a small fixed WGS84 AOI and UTC date interval with a known Sentinel-1 GRD acquisition. Query ASF via `asf_search` using product type and record one complete response fixture with secrets removed.
2. Normalize the fixture into `Scene`; assert ID, acquisition interval, geometry, GRD classification, polarization, and download URL. Verify that a second page is handled without duplicate scenes.
3. Query CDSE `sentinel-1-grd` with the same AOI/time and check the `Product` asset and `next` link. The live Item confirms that `Product.href` is the OData ZIP URL and the Item ID is not the OData UUID. Contract tests retain representative fields; no credentials or full products are stored in Git.
4. For each provider, execute a one-product download with researcher credentials in a manual/scheduled smoke test. Check auth refresh or expiration, redirects, final size/checksum where available, and rerun behavior. Do not put credentials or full products in Git.
5. Compare ASF and CDSE records for the same product name; assert grouping while retaining both provider records and provenance.

The STAC spec says pagination is conveyed by `rel: "next"` links, which may include a POST method, body, merge instruction, or headers. A STAC client such as `pystac-client` can handle this, but the first CDSE fixture should confirm behavior for this deployment. [STAC item search paging examples](https://github.com/radiantearth/stac-api-spec/blob/release/v1.0.0/item-search/examples.md).
