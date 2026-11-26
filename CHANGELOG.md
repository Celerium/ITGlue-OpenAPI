# Changelog

Every change detected in the [IT Glue API documentation](https://api.itglue.com/developer/) is recorded here,
newest first. Versions follow the IT Glue product version; see the README for details.

## 1.118.132.20261126 - 2026-11-26

IT Glue product version **1.118.132** · [API documentation](https://api.itglue.com/developer/)

**209** operations in total — 0 added, 0 removed, 11 modified.

### Modified endpoints
- `GET /documents/{id}`
  - description changed
- `GET /domains`
  - description changed
- `GET /organizations/{organization_id}/relationships/document_folders`
  - description changed
  - parameter added: `with_total_documents_count` (query, optional)
- `GET /organizations/{organization_id}/relationships/document_folders/{id}`
  - description changed
  - parameter added: `with_total_documents_count` (query, optional)
- `GET /organizations/{organization_id}/relationships/documents`
  - description changed
  - parameter added: `filter[document_id]` (query, optional)
- `GET /organizations/{organization_id}/relationships/documents/{id}`
  - description changed
- `GET /organizations/{organization_id}/relationships/domains`
  - description changed
- `GET /organizations/{organization_id}/relationships/password_folders`
  - description changed
  - parameter added: `with_total_passwords_count` (query, optional)
- `GET /organizations/{organization_id}/relationships/password_folders/{id}`
  - description changed
  - parameter added: `with_total_passwords_count` (query, optional)
- `PATCH /documents/{id}/publish`
  - description changed
- `PATCH /organizations/{organization_id}/relationships/documents/{id}/publish`
  - description changed

## 1.118.132.20261114 - 2026-11-14

IT Glue product version **1.118.132** · [API documentation](https://api.itglue.com/developer/)

**209** operations in total — 0 added, 0 removed, 0 modified.

## 1.118.132 - 2026-11-13

IT Glue product version **1.118.132** · [API documentation](https://api.itglue.com/developer/)

Initial specification with **209** operations.
