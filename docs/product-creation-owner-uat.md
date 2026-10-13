# Product creation owner-UAT fix after PR-10

GitHub #46 merged as `bc9f3f10f7fdcfcd7ca4ccb0a13289d1a3af4cb7` before this
finding was addressed. This focused fix starts from that latest `main`; PR-10's
Dashboard, costing and release work is preserved. Owner acceptance and production
approval remain pending.

## Reproduction and cause

An isolated real Flask journey creates a category, subcategory and product with
Product WRITE and no Factory Parameters MODIFY. The unchanged Ubuntu code returns
200 for the first two requests while creating literal-backslash directories;
product creation then returns 500 because its template path is also malformed.
With only the legacy filesystem helpers replaced by their equivalent Windows
results, the same real route creates BOM and capacity files, then returns 500
trying to read the absent factory-root `category_weights.json`. This second run
isolates the reported Windows tail failure; it is **not a native Windows run**.
The [recorded output](evidence/product-creation-owner-uat/before.txt) retains both
reproductions. All operational fixtures were temporary.

## Resulting contract

- Product/category/subcategory creation remains Product WRITE, authorized using
  the canonical registry ID before resolving the same factory's operational key.
  Creation neither requires nor reads/writes financial configuration. The obsolete
  zero-share updater is removed; the old weights reader now reads canonical V2
  paths without generating files or values. Active costing already reads V2.
- Creation uses native `pathlib` joins. Persian names, internal spaces, apostrophes,
  parentheses, plus and hyphens are supported. Traversal, separators, hidden/system
  namespaces, symlink parents and Windows-reserved filenames are rejected.
  Case aliases conflict on Ubuntu as well as Windows. BOM/metadata collisions
  return 409; existing files, including old partial attempts, are preserved.
- Request shape, authorization, capacity, parent directories and product template
  resources are checked before business writes. Capacity is the existing positive
  integer input, never predicted production. Product files are staged and flushed
  in the destination filesystem, capacity is published before BOM, and hierarchy
  metadata is replaced atomically. A shared cross-platform OS lock serializes
  creation and hierarchy refresh. Failed requests compensate only their newly
  published product files/directories and remove staged files.
- The infrastructure `.product-creation.lock` can remain after a failed request;
  it holds no business data. Safe compensation covers ordinary request/write
  failures. Abrupt process termination or power loss is not a transactional
  crash-recovery guarantee; there is no automatic deletion/recovery of old files.
- Hierarchy metadata refreshes on success. Production selection and authorized
  Product/Dashboard options derive their catalog from live same-factory BOM paths,
  so a new product is visible immediately without reading legacy weights.
- The authorized Factory Parameters editor adds missing category/product identities
  from the same-factory hierarchy/catalog **in memory**, with null financial cells.
  Empty categories are visible too. Reads preserve stored values, schemas and
  metadata and do not save these rows. Missing/malformed financial documents are
  shown as unavailable rather than reconstructed from legacy data or numbers.
  Only existing canonical PUT endpoints, requiring Factory Parameters MODIFY,
  save explicit financial inputs. Catalog identity cells render as text and are
  read-only; names containing punctuation are not inserted as HTML.
- Missing shares/predictions retain the existing typed costing-unavailable
  behavior, including the existing ambiguity classification for absent identity
  matches. No cost formulas, V2 schemas, planning periods or authorization levels
  change. User errors are Persian; paths and diagnostic exceptions stay in logs.

## Inspect an old failed attempt without changing its data

Resolve the factory's canonical ID to its registered operational key. In Product
production selection, look for the exact category/subcategory/product. Read and
compare `Factories/<operational_key>/<category>/<subcategory>/<product>.json` and
`<product>_meta.json`, retaining a backup of the original files before any operator
repair. Check BOM contents and capacity; presence of both files can mean the old
request completed its product writes before failing on weights. Do not retry
creation to reset the product: the fix returns 409 and preserves either existing
file, including a BOM-only or capacity-only attempt. Do not delete/reset either
file, recreate legacy weights, or use capacity as a prediction. Enter missing
financial values later through the authorized Factory Parameters editor. A
BOM-only or capacity-only attempt requires a separately reviewed operator repair;
this fix does not automate it.

## Verification

Actual final results, commands, dependency versions, source hashes, JUnit and
synthetic editor screenshots are recorded in the
[evidence README](evidence/product-creation-owner-uat/README.md).
Native Windows owner smoke: repeat category → subcategory → product in a V2-only
factory, verify retry conflict and preserved existing files, then enter approved
shares/predictions under Factory Parameters MODIFY. This remains pending; Ubuntu
and both OS lock adapters are covered by automated checks.
