# Changelog — BS CIF Process Refactoring

## Overview

Five-step refactoring to remove external dependencies (`seventh_key_custom`, `major_installments`) and generalize UAE-specific terminology.

---

## Step 1 [REM] — Remove Installment Features

### Deleted
- `models/installment_line.py` — entire file

### Modified
- `models/__init__.py` — removed `installment_line` import
- `models/cif_form.py` — removed `payment_plan` field
- `models/sale_order.py` — removed `create_invoices_from_lines()` method
- `controllers/cif_controller.py` — removed `payment_plans` from render context
- `views/cif_form_views.xml` — removed `payment_plan` field from view
- `views/cif_individual_web_template.xml` — removed payment plan sections
- `views/cif_company_web_template.xml` — removed payment plan sections
- `data/cif_report_template.xml` — removed payment plan sections

---

## Step 2 [REF] — Generalize UAE-Specific Fields

### Renamed
| Old Field | New Field | Label |
|-----------|-----------|-------|
| `emirates_no` | `national_id` | National ID Number |
| `uae_residency_status` | `residency_status` | Residency Status |

### Files Updated
- `models/cif_form.py`
- `models/res_partner.py`
- `models/cif_change_request.py`
- `controllers/cif_controller.py`
- `views/cif_form_views.xml`
- `views/cif_individual_web_template.xml`
- `views/cif_company_web_template.xml`
- `data/cif_report_template.xml`
- `static/src/js/cif_residency_toggle.js`

---

## Step 3 [REF] — Rename UAE Document Upload System

### Renamed
| Old Name | New Name | Label |
|----------|----------|-------|
| `emirates_id_supporting_docs` | `id_supporting_docs` | ID Supporting Documents |
| `emirates_id_docs` (HTML) | `id_docs` | — |

### Files Updated
- `models/cif_form.py` — field and relation names
- `views/cif_individual_web_template.xml` — form names, element IDs, upload URL
- `views/cif_company_web_template.xml` — form names, element IDs, upload URL
- `static/src/js/cif_multiple_file_upload.js` — element ID references

---

## Step 4 [REM] — Remove `seventh_key_custom` Dependency

### Created
- `models/security_question.py` — standalone base model (formerly inherited from `seventh_key_custom`)
- `views/security_question_views.xml` — standalone views (tree, form, action, menu)
- `static/src/img/7th-key.png` — local copy of logo asset

### Rewritten
- `models/security_question_answer.py` — standalone base model (no longer inherits `seventh_key_custom.security.question.answer`)
- `views/security_question_answer_views.xml` — standalone views (not inheriting `seventh_key_custom`)
- `views/sale_order_views.xml` — now inherits from `sale.view_order_form` (was inheriting `seventh_key_custom.view_sale_order_form_inherit_seventh_key_custom`)

### Modified
- `__manifest__.py` — removed `seventh_key_custom` from depends, added `major_installments` (interim); added local data files
- `security/ir.model.access.csv` — added access entries for `security.question` and `security.question.answer`
- All `views/cif_*.xml` — updated logo URL from `/seventh_key_custom/` → `/bs_cif_process/`
- All web templates — updated all `/seventh_key_custom/` URL references → `/bs_cif_process/`
- `data/cif_report_template.xml` — updated logo URL
- `data/cif_mail_template.xml` — updated logo URL

---

## Step 5 [REM] — Refactor Purchaser Dependency to Single Partner

### Deleted
- `models/sale_order_purchaser.py` — entire file
- `views/sale_order_purchaser_views.xml` — entire file

### Modified — `models/cif_change_request.py`
- Removed `purchaser_line_id` field
- Changed `sale_order_id` and `partner_id` from related fields to direct Many2one fields
- Removed `purchaser_line` parameter from `_build_cif_change_composer_action()`
- `snapshot_share_percentage` now hardcoded to `0.0` (no longer dynamic from purchaser)

### Modified — `models/cif_form.py`
- `action_send_cif_change_request()` — removed `sale.order.purchaser` search; uses `self.created_partner_id` directly

### Modified — `models/sale_order.py`
- Removed `sale_order_purchaser_ids` references from `_compute_has_cif_form` and `action_view_cif_forms`

### Modified — `controllers/cif_controller.py`
- Removed methods: `_get_next_purchaser_slot`, `_check_partner_not_duplicate_in_purchasers`, `_check_email_unique_for_sale_order`, `_ensure_purchaser_line`
- Removed `sale.order.purchaser` creation in individual and company submit handlers
- Changed CIF change request workflow to use `change_req.cif_form_id` / `change_req.partner_id` directly (was `purchaser_line`)
- Removed `immutable_share` variable

### Modified — Web Templates
- `views/cif_individual_web_template.xml` — changed `prefill_share_percentage` → `existing_cif.shareholder_percentage`
- `views/cif_company_web_template.xml` — changed `prefill_share_percentage` → `existing_cif.shareholder_percentage`

### Modified — `views/cif_change_request_views.xml`
- Removed `purchaser_line_id` from tree and form views

### Modified — `__manifest__.py`
- Removed `major_installments` from depends
- Replaced with direct dependencies: `mail`, `sale`, `website`
- Removed `views/sale_order_purchaser_views.xml` from data list

---

## Final `__manifest__.py` Dependencies

```python
'depends': [
    'mail',
    'sale',
    'website',
],
```
