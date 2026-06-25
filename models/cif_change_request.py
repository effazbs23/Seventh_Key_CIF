# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import base64
import uuid
import hashlib
import secrets
from datetime import timedelta


class CIFChangeRequest(models.Model):
    _name = 'cif.change.request'
    _description = 'CIF Change Request'
    _inherit = ['mail.thread']
    _rec_name = 'name'
    _order = 'create_date desc'

    name = fields.Char(
        string='Reference',
        required=True,
        copy=False,
        readonly=True,
        default='New',
        tracking=True,
    )

    token = fields.Char(
        string='Token',
        required=True,
        copy=False,
        readonly=True,
        index=True,
        default=lambda self: base64.urlsafe_b64encode(uuid.uuid4().bytes).decode().removesuffix('=='),
        tracking=True,
    )

    sale_order_id = fields.Many2one('sale.order', string='Sale Order', required=True, ondelete='cascade', tracking=True)
    partner_id = fields.Many2one('res.partner', string='Partner', tracking=True)

    # Explicit tag to the CIF form to keep a stable history on the CIF itself.
    cif_form_id = fields.Many2one('cif.form', string='CIF Form', required=True, ondelete='cascade', tracking=True)

    email_to = fields.Char(string='Email To', required=True, tracking=True)

    # Snapshot (data as it was when the change request was created)
    snapshot_partner_name = fields.Char(string='Snapshot Partner Name', readonly=True, copy=False, tracking=True)
    snapshot_partner_email = fields.Char(string='Snapshot Partner Email', readonly=True, copy=False, tracking=True)
    snapshot_share_percentage = fields.Float(string='Snapshot Share %', readonly=True, copy=False, tracking=True)
    snapshot_cif_no = fields.Char(string='Snapshot CIF No.', readonly=True, copy=False, tracking=True)

    state = fields.Selection([
        ('draft', 'Draft'),
        ('done', 'Done'),
        ('expired', 'Expired'),
    ], default='draft', tracking=True)

    # No expiry input from wizard anymore; request can be expired manually.
    expires_at = fields.Datetime(string='Expired At', tracking=True)

    sent_by = fields.Many2one('res.users', string='Requested By', default=lambda self: self.env.user, readonly=True, tracking=True)

    opened_at = fields.Datetime(string='Opened At', tracking=True)
    done_at = fields.Datetime(string='Done At', tracking=True)
    used_ip = fields.Char(string='Used IP')
    used_user_agent = fields.Char(string='User Agent')

    # =========================================================
    # == Email verification (for Change CIF link access)    ==
    # =========================================================

    is_email_verified = fields.Boolean(string='Email Verified', default=False, tracking=True)
    email_verified_at = fields.Datetime(string='Email Verified At', tracking=True)

    # =========================================================
    # ==   New Email Change Tracking (for CIF data changes) ==
    # =========================================================

    new_email = fields.Char(
        string='New Email Address',
        tracking=True,
        help='New email address to be verified and updated in CIF data'
    )
    is_new_email_verified = fields.Boolean(
        string='New Email Verified',
        default=False,
        tracking=True,
        help='True when the new email has been verified via OTP'
    )
    new_email_verified_at = fields.Datetime(string='New Email Verified At', tracking=True)
    new_email_otp_hash = fields.Char(string='New Email OTP Hash', copy=False)
    new_email_otp_expires_at = fields.Datetime(string='New Email OTP Expires At')
    new_email_otp_attempts = fields.Integer(string='New Email OTP Attempts', default=0)
    new_email_otp_max_attempts = fields.Integer(string='New Email OTP Max Attempts', default=3)
    new_email_otp_sent_at = fields.Datetime(string='New Email OTP Sent At')

    # =========================================================
    # ==   Security Questions Verification (Additional Layer) ==
    # =========================================================

    is_security_verified = fields.Boolean(
        string='Security Questions Verified',
        default=False,
        tracking=True,
        help='True when purchaser has correctly answered security questions'
    )
    security_verified_at = fields.Datetime(string='Security Verified At', tracking=True)
    security_attempts = fields.Integer(string='Security Question Attempts', default=0)
    security_max_attempts = fields.Integer(string='Security Max Attempts', default=5)
    security_locked_until = fields.Datetime(
        string='Security Locked Until',
        help='Timestamp until which security verification is locked due to failed attempts'
    )

    # =========================================================
    # ==   Change CIF public workflow hardening (step tokens) ==
    # =========================================================

    workflow_state = fields.Selection([
        ('draft', 'Draft'),
        ('email_verified', 'Email Verified'),
        ('form_opened', 'Form Opened'),
        ('submitted', 'Submitted'),
        ('done', 'Done'),
        ('expired', 'Expired'),
    ], default='draft', tracking=True)

    current_step = fields.Selection([
        ('email', 'Email Verification'),
        ('otp', 'OTP Verification'),
        ('security', 'Security Questions'),
        ('form', 'Form Access'),
        ('submit', 'Submission'),
    ], copy=False)

    step_token_hash = fields.Char(string='Step Token Hash', copy=False)
    step_token_expires_at = fields.Datetime(string='Step Token Expires At', copy=False)

    def _normalize_email(self, email):
        return (email or '').strip().lower()

    def _get_registered_email(self):
        """Email address that must be verified for this request.

        Prefer CIF-tagged partner email, fallback to partner, then email_to.
        """
        self.ensure_one()
        partner = (self.cif_form_id.created_partner_id if self.cif_form_id else False) or self.partner_id
        return self._normalize_email((partner.email if partner else False) or self.email_to)


    # =========================================================
    # ==   New Email OTP Methods (for CIF data email changes) ==
    # =========================================================

    def generate_new_email_otp(self, expires_minutes=2):
        """Generate and store a time-bound OTP for new email verification.

        This is used when a user wants to change their email in CIF data.
        Default validity is 2 minutes.
        """
        self.ensure_one()

        if not self.new_email:
            raise ValidationError(_("New email address is required to generate verification code."))

        # Check cooldown for new email OTP
        if self.new_email_otp_sent_at:
            delta = fields.Datetime.now() - self.new_email_otp_sent_at
            if delta.total_seconds() < 60:  # 60 seconds cooldown
                raise ValidationError(_("Please wait before requesting a new verification code."))

        # Generate OTP
        otp_plain = ''.join(secrets.choice('0123456789') for _ in range(6))
        now = fields.Datetime.now()
        expires_at = now + timedelta(minutes=expires_minutes)

        # Hash with new_email to differentiate from main email OTP
        raw = f"{self.token or ''}:new_email:{otp_plain}".encode('utf-8')
        otp_hash = hashlib.sha256(raw).hexdigest()

        self.write({
            'new_email_otp_hash': otp_hash,
            'new_email_otp_expires_at': expires_at,
            'new_email_otp_attempts': 0,
            'new_email_otp_sent_at': now,
        })
        return otp_plain

    def send_new_email_otp(self, otp_plain, email_to):
        """
        Send OTP email to the new email address.
        Similar to send_email_otp but for new email verification.
        """
        self.ensure_one()

        if not email_to:
            raise ValidationError(_("Email address is required to send verification code."))

        if not otp_plain:
            raise ValidationError(_("Verification code is required."))

        # Get email template for new email OTP
        try:
            template = self.env.ref('bs_cif_process.email_template_new_email_otp', raise_if_not_found=False)
            if not template:
                # Fallback to regular OTP template if new email template doesn't exist
                template = self.env.ref('bs_cif_process.email_template_email_otp')
        except Exception:
            raise ValidationError(_("Email template for verification code not found."))

        # Prepare context
        ctx = self.env.context.copy()
        ctx.update({
            'otp_code': otp_plain,
            'recipient_email': email_to,
            'recipient_name': self.partner_id.name if self.partner_id else 'Customer',
        })

        # Send email
        try:
            template.with_context(ctx).send_mail(
                self.id,
                email_values={'email_to': email_to},
                force_send=True,
                raise_exception=True
            )
        except Exception as e:
            import logging
            _logger = logging.getLogger(__name__)
            _logger.error(f"Failed to send new email OTP: {e}")
            raise ValidationError(_("Failed to send verification email. Please try again."))

        return True

    def verify_new_email_otp(self, otp_plain):
        """Verify OTP for new email. On success, marks new email as verified."""
        self.ensure_one()

        if not self.new_email:
            raise ValidationError(_("No new email address found."))

        if not self.new_email_otp_hash or not self.new_email_otp_expires_at:
            raise ValidationError(_("No verification code found. Please request a new code."))

        if fields.Datetime.now() > self.new_email_otp_expires_at:
            raise ValidationError(_("Verification code has expired. Please request a new code."))

        # Check lockout
        if self.new_email_otp_attempts >= (self.new_email_otp_max_attempts or 3):
            raise ValidationError(_("Maximum verification attempts exceeded. Please request a new code."))

        # Increment attempt counter first
        self.new_email_otp_attempts += 1

        # Verify OTP
        raw = f"{self.token or ''}:new_email:{(otp_plain or '').strip()}".encode('utf-8')
        computed_hash = hashlib.sha256(raw).hexdigest()

        if computed_hash != self.new_email_otp_hash:
            remaining = (self.new_email_otp_max_attempts or 3) - self.new_email_otp_attempts
            if remaining > 0:
                raise ValidationError(_("Invalid verification code. Attempts remaining: %s") % remaining)
            raise ValidationError(_("Invalid verification code. Maximum attempts reached. Please request a new code."))

        # Success - mark new email as verified
        self.write({
            'is_new_email_verified': True,
            'new_email_verified_at': fields.Datetime.now(),
            'new_email_otp_hash': False,
            'new_email_otp_expires_at': False,
        })
        return True

    def reset_email_verification(self):
        """Reset verification state so a new verification can be started."""
        for rec in self:
            rec.write({
                'is_email_verified': False,
                'email_verified_at': False,
                # Reset new email verification
                'new_email': False,
                'is_new_email_verified': False,
                'new_email_verified_at': False,
                'new_email_otp_hash': False,
                'new_email_otp_expires_at': False,
                'new_email_otp_attempts': 0,
                'new_email_otp_sent_at': False,
                # Reset security verification as well
                'is_security_verified': False,
                'security_verified_at': False,
                'security_attempts': 0,
                'security_locked_until': False,
                # Reset hardened workflow state
                'workflow_state': 'draft',
                'current_step': False,
                'step_token_hash': False,
                'step_token_expires_at': False,
            })

    # =========================================================
    # ==   Security Questions Verification Methods           ==
    # =========================================================

    def verify_security_questions(self, answers_dict):
        """Verify security question answers.

        Args:
            answers_dict: Dictionary mapping question_id to answer text

        Returns:
            True if verification successful

        Raises:
            ValidationError if verification fails or locked
        """
        self.ensure_one()
        self._check_not_expired()

        # Check if security verification is locked
        if self.security_locked_until and fields.Datetime.now() < self.security_locked_until:
            raise ValidationError(_(
                'Security verification is temporarily locked due to multiple failed attempts. '
                'Please try again later.'
            ))

        # Must have completed email OTP verification first
        if not self.is_email_verified:
            raise ValidationError(_('Email verification must be completed before security questions.'))

        # Get the security question answers from the CIF form (not from partner)
        cif_form = self.cif_form_id
        if not cif_form:
            raise ValidationError(_('CIF form not found for verification.'))

        stored_answers = cif_form.security_answer_ids
        if not stored_answers:
            raise ValidationError(_('No security questions configured for this CIF form.'))

        # Validate answers
        all_correct = True
        for stored_answer in stored_answers:
            submitted_answer = answers_dict.get(str(stored_answer.question_id.id), '').strip().lower()
            expected_answer = (stored_answer.answer or '').strip().lower()

            if submitted_answer != expected_answer:
                all_correct = False
                break

        # Record attempt
        self.security_attempts += 1

        if not all_correct:
            # Lock after max attempts
            if self.security_attempts >= (self.security_max_attempts or 5):
                self.write({
                    'security_locked_until': fields.Datetime.now() + timedelta(minutes=10)
                })
                raise ValidationError(_(
                    'Security verification failed. Maximum attempts exceeded. '
                    'Verification locked for 10 minutes.'
                ))

            raise ValidationError(_(
                'Security verification failed. Please check your answers.'))

        # Success - mark as verified
        self.write({
            'is_security_verified': True,
            'security_verified_at': fields.Datetime.now(),
            'security_attempts': 0,
            'security_locked_until': False,
        })
        return True

    def reset_security_verification(self):
        """Reset security verification state."""
        for rec in self:
            rec.write({
                'is_security_verified': False,
                'security_verified_at': False,
                'security_attempts': 0,
                'security_locked_until': False,
            })

    def _check_security_verified(self):
        """Check if security questions have been verified.

        Raises ValidationError if not verified or locked.
        """
        self.ensure_one()

        # Check if locked
        if self.security_locked_until and fields.Datetime.now() < self.security_locked_until:
            raise ValidationError(_(
                'Security verification is temporarily locked. Please try again later.'
            ))

        # Check if verified
        if not self.is_security_verified:
            raise ValidationError(_('Security question verification required.'))

        return True

    def action_send_change_request_composer(self):
        """
        Open mail compose wizard to send CIF change request email.
        ✅ Posts to chatter when email is sent (using composition_mode='comment').
        """
        self.ensure_one()

        # Get email template
        try:
            template = self.env.ref('bs_cif_process.email_template_cif_change_request')
        except ValueError:
            raise ValidationError(_('Email template for CIF change request is missing. Please contact administrator.'))

        # Build change URL with token
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url') or ''
        change_url = f"{base_url}/client-information-form/change?token={self.token}"

        # Get partner
        partner = self.partner_id

        # Prepare context for compose wizard
        ctx = {
            'default_model': 'cif.change.request',
            'default_res_ids': self.ids,
            'default_use_template': True,
            'default_template_id': template.id,
            'default_composition_mode': 'comment',
            'default_partner_ids': [(6, 0, [partner.id])] if partner else [],
            'change_url': change_url,
            'force_email': True,
            'mail_explicit_recipients_only': True,
        }

        return {
            'type': 'ir.actions.act_window',
            'name': _('Send CIF Change Request'),
            'res_model': 'mail.compose.message',
            'view_mode': 'form',
            'target': 'new',
            'context': ctx,
        }

    @api.model
    def _build_cif_change_composer_action(self, sale_order, partner, email_to, cif_form):
        """
        Single source of truth for opening the CIF Change Request email composer.

        Generates a secure token **in memory**, constructs the CIF update link, and
        returns the ``ir.actions.act_window`` dict that opens ``mail.compose.message``
        pre-loaded with the ``email_template_cif_change_request`` template.

        Called from:
        - ``cif.form.action_send_cif_change_request``        (CIF form button)

        No DB record is created here.  The ``on_send_callback`` registered in the
        context ensures that ``post_send_create`` is called **only** when the user
        clicks Send.
        """
        import secrets

        # Fail fast on missing template before opening the composer
        template = self.env.ref(
            'bs_cif_process.email_template_cif_change_request',
            raise_if_not_found=False,
        )
        if not template:
            raise ValidationError(_(
                "The 'CIF Change Request' email template could not be found. "
                "Please ensure the 'bs_cif_process' module is up to date."
            ))

        token = secrets.token_urlsafe(32)
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url') or ''
        cif_update_link = f"{base_url}/client-information-form/change?token={token}"

        return {
            'type': 'ir.actions.act_window',
            'name': _('Send CIF Change Request'),
            'res_model': 'mail.compose.message',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_model': 'sale.order',
                'default_res_ids': sale_order.ids,
                'default_composition_mode': 'comment',
                'default_use_template': True,
                'default_template_id': template.id,
                'default_partner_ids': [(6, 0, [partner.id])] if partner else [],
                'force_email': True,
                'mail_explicit_recipients_only': True,
                'mail_notify_author': True,
                # Injected into the template body via ctx.get('cif_update_link')
                'cif_update_link': cif_update_link,
                # ── Universal on-Send callback ────────────────────────────────
                'on_send_callback_model': 'cif.change.request',
                'on_send_callback_method': 'post_send_create',
                'on_send_callback_kwargs': {
                    'cif_form_id': cif_form.id,
                    'partner_id': partner.id if partner else False,
                    'sale_order_id': sale_order.id,
                    'email_to': email_to,
                    'token': token,
                    'cif_update_link': cif_update_link,
                },
            },
        }

    @api.model
    def post_send_create(self, cif_form_id, partner_id, sale_order_id, email_to,
                         token, cif_update_link):
        """
        Universal on_send_callback — called by mail.compose.message._action_send_mail
        ONLY when the user clicks **Send**.

        Creates the cif.change.request record with the pre-generated token and
        posts an audit-trail link on the Sale Order chatter.

        Never called when the user closes (✕) the compose dialog.
        """
        from markupsafe import Markup

        change_req = self.create({
            'cif_form_id': cif_form_id,
            'partner_id': partner_id,
            'sale_order_id': sale_order_id,
            'email_to': email_to,
            'token': token,
            'state': 'draft',
        })

        # Post chatter link on the Sale Order
        sale_order = self.env['sale.order'].browse(sale_order_id)
        if sale_order.exists():
            base_url = (
                self.env['ir.config_parameter'].sudo().get_param('web.base.url') or ''
            )
            record_url = (
                f"{base_url}/web#model=cif.change.request"
                f"&id={change_req.id}&view_type=form"
            )
            record_link = Markup('<a href="%s">%s</a>') % (record_url, change_req.name)
            sale_order.message_post(
                body=Markup("CIF Change Request sent: {}").format(record_link),
                subject=_("CIF Change Request Created"),
                subtype_xmlid='mail.mt_note',
            )

        return change_req

    def action_send_change_request_email(self):
        """
        Send CIF change request email automatically (without compose wizard).
        Posts to chatter for audit trail.
        Use this for automated sending (e.g., from scheduled actions).
        For manual sending with compose wizard, use _build_cif_change_composer_action().
        """
        self.ensure_one()

        # Get email template (model: sale.order)
        template = self.env.ref(
            'bs_cif_process.email_template_cif_change_request',
            raise_if_not_found=False,
        )
        if not template:
            raise ValidationError(_('Email template for CIF change request is missing. Please contact administrator.'))

        if not self.sale_order_id:
            raise ValidationError(_('No Sale Order linked to this CIF Change Request.'))

        # Build change URL with token
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url') or ''
        cif_update_link = f"{base_url}/client-information-form/change?token={self.token}"

        # Render against sale.order, inject link via context
        ctx = self.env.context.copy()
        ctx['cif_update_link'] = cif_update_link

        template.with_context(ctx).send_mail(
            self.sale_order_id.id,
            email_values={'email_to': self.email_to},
            force_send=True,
            raise_exception=True,
        )

        # Post to chatter for audit trail
        self.message_post(
            body=_('CIF Change request email sent to %s.') % (self.email_to,),
            subject=_('CIF Change Request Sent')
        )

        # Also log in sale order chatter for visibility
        if self.sale_order_id:
            self.sale_order_id.message_post(
                body=_('CIF Change request sent to %s for %s (CIF: %s).') % (
                    self.email_to,
                    self.partner_id.display_name if self.partner_id else 'Unknown',
                    self.cif_form_id.cif_no if self.cif_form_id else 'N/A'
                ),
                subject=_('CIF Change Request Sent')
            )

        return True

    def action_expire(self):
        for rec in self:
            if rec.state not in ('done', 'expired'):
                rec.write({'state': 'expired', 'workflow_state': 'expired', 'expires_at': fields.Datetime.now()})

    def _check_not_expired(self):
        self.ensure_one()
        if self.state == 'expired' or self.workflow_state == 'expired':
            raise ValidationError(_("This change request link has expired."))
        if self.state == 'done' or self.workflow_state in ('done',):
            raise ValidationError(_("This change request is no longer valid."))

    def mark_opened(self, ip=None, ua=None):
        for rec in self:
            if not rec.opened_at:
                rec.opened_at = fields.Datetime.now()
            if ip:
                rec.used_ip = ip
            if ua:
                rec.used_user_agent = ua
            # Only move once, on first successful form open.
            if rec.workflow_state == 'email_verified':
                rec._transition_workflow('form_opened')

    def mark_done(self, ip=None, ua=None):
        for rec in self:
            rec.state = 'done'
            rec.workflow_state = 'done'
            rec.done_at = fields.Datetime.now()
            if ip:
                rec.used_ip = ip
            if ua:
                rec.used_user_agent = ua

    def _compute_snapshot_values(self):
        """Take a lightweight snapshot of key values at request time.

        Important: snapshots should reflect the partner tagged on the CIF (created_partner_id),
        because Change CIF updates must apply to that partner.
        """
        for rec in self:
            cif = rec.cif_form_id
            partner = (cif.created_partner_id if cif else False) or rec.partner_id
            rec.snapshot_partner_name = partner.display_name if partner else False
            rec.snapshot_partner_email = (partner.email or '').strip() if partner else (rec.email_to or '').strip()
            rec.snapshot_share_percentage = 0.0
            rec.snapshot_cif_no = cif.cif_no if cif else False

    @api.model_create_multi
    def create(self, vals_list):
        # Ensure reference is assigned from sequence
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('cif.change.request.sequence') or 'New'

        records = super().create(vals_list)
        for rec in records:
            # Snapshot the existing data at request time
            rec._compute_snapshot_values()
        return records

    # =========================================================
    # ==   Change CIF public workflow hardening (step tokens) ==
    # =========================================================

    def _compute_step_token_hash(self, step, token_plain):
        self.ensure_one()
        raw = f"{self.token or ''}:{step}:{token_plain}".encode('utf-8')
        return hashlib.sha256(raw).hexdigest()

    def issue_step_token(self, step, ttl_minutes=10):
        """Issue a short-lived single-use token bound to this request and purpose (step)."""
        self.ensure_one()
        token_plain = base64.urlsafe_b64encode(secrets.token_bytes(24)).decode().removesuffix('==')
        now = fields.Datetime.now()
        self.write({
            'current_step': step,
            'step_token_hash': self._compute_step_token_hash(step, token_plain),
            'step_token_expires_at': now + timedelta(minutes=ttl_minutes),
        })
        return token_plain

    def _assert_step_token(self, step, token_plain):
        self.ensure_one()
        self._check_not_expired()

        if not token_plain:
            raise ValidationError(_("Missing security token."))
        if not self.step_token_hash or not self.step_token_expires_at or not self.current_step:
            raise ValidationError(_("Security token is not initialized. Please restart the process from the email link."))
        if self.current_step != step:
            raise ValidationError(_("Invalid security token for this step. Please restart the process from the email link."))
        if fields.Datetime.now() > self.step_token_expires_at:
            raise ValidationError(_("Security token has expired. Please restart the process from the email link."))

        expected = self._compute_step_token_hash(step, (token_plain or '').strip())
        if expected != self.step_token_hash:
            raise ValidationError(_("Invalid security token. Please restart the process from the email link."))

    def consume_step_token(self, step, token_plain):
        """Validate and immediately invalidate the current step token (single-use)."""
        self.ensure_one()
        self._assert_step_token(step, token_plain)
        self.write({
            'step_token_hash': False,
            'step_token_expires_at': False,
        })
        return True

    def _transition_workflow(self, new_state):
        self.ensure_one()
        allowed = {
            'draft': {'email_verified'},
            'email_verified': {'form_opened'},
            'form_opened': {'submitted'},
            'submitted': {'done'},
        }
        if self.workflow_state in ('expired', 'done'):
            raise ValidationError(_("This change request is no longer valid."))
        self.workflow_state = new_state
