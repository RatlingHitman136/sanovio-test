# Catalog seed

Transcribed from the client's example catalogs (ARCHITECTURE §21), page by page:

| File | Family | Source |
|---|---|---|
| `bbraun.json` | Injekt® Luer Lock Solo | `product_catalog_01.pdf`, page 6 |
| `bbraun.json` | Sterican® Standard-Einmalkanülen | `product_catalog_01.pdf`, page 26 |
| `bd.json` | BD Plastipak™ Luer-Lok™ / Luer | `product_catalog_02.pdf`, page 13 |
| `bd.json` | BD Emerald™ Luer | `product_catalog_02.pdf`, page 12 |
| `bd.json` | BD Microlance™ Injektionskanülen | `product_catalog_02.pdf`, page 6 |

`source_row` holds each size row as printed, because that text is what the core parsers read.
`properties_text` and `description` are the printed product texts `normalize_item` reads.
