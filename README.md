# BS CIF Process

**Version:** 18.0.1.0.0 | **License:** LGPL-3 | **Category:** Sales

## Overview

The BS CIF Process module manages the complete **Client Information Form (CIF)** workflow for real estate sales. It provides web-based forms for individual and company clients to submit their KYC information, including identity document uploads, signature capture, email OTP verification, and security-question-based identity verification.

## Key Features

- **Individual & Company CIF Forms** — Public-facing web forms with token-based access for customers to submit their information.
- **Email OTP Verification** — 6-digit OTP sent via email to verify primary and alternate email addresses before submission.
- **Security Question Verification** — Customers configure 3 security questions during initial CIF submission; these must be answered correctly in the Change CIF flow.
- **CIF Change Request Workflow** — A multi-step, token-gated process (email verification → security questions → form access → submission) allowing customers to update their CIF data via a secure public link.
- **CIF Request Session Management** — Token-based access with configurable submission quotas and atomic consumption to prevent over-submission.
- **Document Upload Support** — Passport and Emirates ID supporting documents with multiple file upload.
- **Signature Capture** — Draw or upload signature images during form submission.
- **Sale Order Integration** — CIF forms are linked to sale orders via purchaser slots; the sale order moves to an `in_cif` state during collection.
- **Multi-Company Security Rules** — Record rules scoped to `company_ids` for multi-company isolation.
- **Agent/Agency Tracking** — Automatically populates agent details on the CIF form from the sale order's assigned agent.

## Module Structure

| Path | Description |
|------|-------------|
| `models/cif_form.py` | Core `cif.form` model — all CIF fields (personal info, documents, verification flags) and workflow actions (accept/reject/send change request) |
| `models/cif_change_request.py` | `cif.change.request` model — token-gated multi-step change workflow with step tokens, email OTP, security questions, and snapshot tracking |
| `models/cif_request_session.py` | `cif.request.session` model — token generation, submission quotas, atomic slot consumption via `SELECT ... FOR UPDATE` |
| `models/email_otp.py` | `email.otp` model — 6-digit OTP generation, verification, resend with 60s cooldown, and expiry (2 min) |
| `models/security_question_answer.py` | Inherits `security.question.answer` to add `cif_form_id` linkage |
| `models/sale_order.py` | Extends `sale.order` with CIF states (`in_cif`), session tracking, CIF form URL generation, and send action |
| `models/sale_order_purchaser.py` | Extends `sale.order.purchaser` with `cif_form_id` linkage |
| `models/res_partner.py` | Extends `res.partner` with `cif_form_count` smart button |
| `models/mail_compose_message.py` | Universal post-send callback for CIF change request creation after email send |
| `models/installment_line.py` | Extends `installment.line` to allow invoice creation in CIF/EOI/booking states |
| `models/utils.py` | Shared constants (`PAYMENT_TYPE_OPTIONS`) |
| `controllers/cif_controller.py` | All public HTTP routes for individual/company CIF submission and Change CIF workflow (1212 lines) |
| `controllers/cif_email_otp_controller.py` | AJAX endpoints for email OTP send/verify/resend/status (new CIF and Change CIF) |
| `wizards/cif_form_reject_reason_wizard.py` | Transient model for rejection reason input |
| `views/` | 15+ view files including backend tree/form views, web portal templates, and QWeb report templates |
| `static/src/js/` | Frontend JavaScript for residency toggle, multiple file upload, and security question validation |
| `security/` | Record rules (multi-company) and model access CSV |

## Dependencies

- `seventh_key_custom` — A custom module that provides:
  - `sale.order.purchaser` model (purchaser slots on sale orders)
  - `installment.option` and `installment.line` models
  - `security.question` and `security.question.answer` models
  - Custom fields on `sale.order`: `share_percentage`, `agent_code`, `agent_id.representative`, custom states (`in_cif`, `in_eoi`, `booking_sent`, `booking_signed`, `spa_sent`, `spa_signed`, `oqood_started`, `oqood_completed`)
  - Custom fields on `res.partner`: `agent_code`, `trade_license_no`, `representative`, `middle_name`, `email_address`, `payment_type`, `passport_no`, `emirates_no`, `uae_residency_status`, `source_of_income`, `signature`
  - `send.form.wizard` transient model

- Standard Odoo modules: `sale`, `mail`, `web`, `website`

## Can This Run in Odoo 18 Community Edition?

**Yes, `bs_cif_process` itself can — it has zero Enterprise-only dependencies.**

However, its sole dependency `seventh_key_custom` **cannot** run on CE without modification, because it inherits models from Odoo Enterprise `sign` and `documents` modules. This makes the full stack (`bs_cif_process` + `seventh_key_custom`) require Enterprise.

### Why `bs_cif_process` Works on CE

The `bs_cif_process` module exclusively uses:
- `mail.thread`, `mail.activity.mixin` ✓
- `website` controllers with `auth='public'` ✓
- QWeb templates for web forms ✓
- `ir.attachment` for file uploads ✓
- `ir.sequence` for auto-numbering ✓
- Standard `res.partner`, `sale.order`, `mail.compose.message` ✓
- Multi-company record rules ✓
- Standard Python libs: `pytz`, `hashlib`, `secrets`, `uuid`, `base64`, `json`, `re`, `logging` ✓
- `markupsafe` (bundled with Odoo) ✓

This module **does not** reference `sign.*`, `documents.*`, or any other Enterprise-only model or XML ID.

### Why `seventh_key_custom` (the Dependency) Requires Enterprise

| File | Enterprise Model/XML ID | Module | Impact |
|------|------------------------|--------|--------|
| `models/sign_template.py` | `sign.template` (inherit) | `sign` (Enterprise) | Fails at model load |
| `models/sign_request.py` | `sign.request` (inherit) | `sign` (Enterprise) | Fails at model load |
| `models/sign_item.py` | `sign.item` (inherit) | `sign` (Enterprise) | Fails at model load |
| `models/documents_document.py` | `documents.document` (inherit) | `documents` (Enterprise) | Fails at model load |
| `wizards/sign_send_request.py` | `sign.send.request` (inherit) | `sign` (Enterprise) | Fails at model load |
| `controllers/eoi_controller.py` | XML ID `sign.sign_item_type_signature` | `sign` (Enterprise) | Runtime error |
| `controllers/eoi_controller.py` | XML ID `sign.sign_item_role_customer` | `sign` (Enterprise) | Runtime error |
| `wizards/sign_send_request.py` | XML ID `sign.sign_item_role_user` | `sign` (Enterprise) | Runtime error |

These **5 model inheritances** and **3 XML ID references** make `seventh_key_custom` incompatible with CE.

### Workaround: Run `bs_cif_process` on CE

To run `bs_cif_process` on Odoo 18 CE, create a lightweight adapter module (instead of depending on `seventh_key_custom`) that provides only what `bs_cif_process` needs — none of which requires Enterprise:

**Models to define in the adapter:**
| Model | Purpose |
|-------|---------|
| `sale.order.purchaser` | Purchaser slots on sale orders, linked to CIF forms and partners |
| `installment.option` | Payment plan options for sale orders |
| `installment.line` | Installment lines with invoice creation |
| `security.question` | Security question definitions |
| `security.question.answer` | User-provided security answers |
| `send.form.wizard` | Transient wizard for customer type selection |

**Custom fields on `sale.order`:**
| Field | Purpose |
|-------|---------|
| `share_percentage` (Float) | Remaining share validation |
| `purchasers_count` (Integer) | Allowed submission count |
| `sale_order_purchaser_ids` (One2many) | Purchaser slot management |
| `installment_option_custom` (Many2one → `installment.option`) | Payment plan |

**Custom fields on `res.partner`:**
| Field | Purpose |
|-------|---------|
| `middle_name` (Char) | Individual name |
| `email_address` (Char) | Alternate email |
| `passport_no` (Char) | Identity document |
| `emirates_no` (Char) | Identity document |
| `payment_type` (Selection) | Preferred payment type |
| `uae_residency_status` (Selection) | Resident/non-resident |
| `source_of_income` (Char) | Income source |
| `signature` (Binary) | Signature image |
| `security_answer_ids` (One2many) | Security answers |

**Custom `sale.order` states to add:** `in_cif`, `in_eoi`.

(The other states — `booking_sent`, `booking_signed`, `spa_sent`, `spa_signed`, `oqood_started`, `oqood_completed` — are not referenced by `bs_cif_process`.)

This adapter module depends on `contacts`, `sale`, `account`, and `website` — all CE — and removes the transitive Enterprise dependency entirely.
