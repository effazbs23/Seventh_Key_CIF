# -*- coding: utf-8 -*-
"""
Universal post-send callback for mail.compose.message.

Any button that opens a compose wizard can register side-effects that
should run ONLY when the user clicks Send — not when they close (✕) the
dialog.  Pass three keys in the action context:

    on_send_callback_model   : str   e.g. 'cif.change.request'
    on_send_callback_method  : str   e.g. 'post_send_create'
    on_send_callback_kwargs  : dict  any JSON-serialisable data the
                                     method needs

_action_send_mail() calls the method dynamically after the email is
sent.  If the user closes the dialog, _action_send_mail is never called
→ no DB writes → no orphan records.
"""

import logging

from odoo import models, _
from odoo.tools.mail import email_split

_logger = logging.getLogger(__name__)


class MailComposeMessage(models.TransientModel):
    _inherit = 'mail.compose.message'

    def _action_send_mail(self, auto_commit=False):
        result = super()._action_send_mail(auto_commit=auto_commit)
        ctx = self.env.context

        # ── Universal post-send callback ──────────────────────────────────────
        # Caller passes on_send_callback_model + on_send_callback_method +
        # on_send_callback_kwargs in context when opening the compose wizard.
        # The method is an @api.model method on that model.
        callback_model = ctx.get('on_send_callback_model')
        callback_method = ctx.get('on_send_callback_method')
        if callback_model and callback_method:
            kwargs = ctx.get('on_send_callback_kwargs') or {}
            try:
                getattr(self.env[callback_model], callback_method)(**kwargs)
            except Exception:
                _logger.exception(
                    'on_send_callback failed: %s.%s  kwargs=%s',
                    callback_model, callback_method, kwargs,
                )

        # ── Legacy: CIF send-form email tracking ─────────────────────────────
        if not ctx.get('is_cif_mail'):
            return result

        if self.composition_mode != 'comment' or self.model != 'sale.order':
            return result

        res_ids = self._evaluate_res_ids()
        if not res_ids:
            return result

        to_emails = []
        if self.partner_ids:
            to_emails += [p.email for p in self.partner_ids if p.email]
        if self.email_to:
            to_emails += email_split(self.email_to)
        to_emails = [e.strip().lower() for e in to_emails if e.strip()]

        cc_emails = []
        if hasattr(self, '_bs_get_effective_cc'):
            cc_header = self._bs_get_effective_cc({})
            if cc_header:
                cc_emails = [e.strip().lower() for e in email_split(cc_header) if e.strip()]

        all_emails = to_emails + cc_emails

        if not all_emails:
            return result

        for order in self.env['sale.order'].browse(res_ids):
            existing_to = order.cif_mail_sent_to or ''
            existing_to_emails = set(e.strip().lower() for e in email_split(existing_to) if e.strip())

            for email in to_emails:
                if email not in existing_to_emails:
                    existing_to_emails.add(email)
            order.cif_mail_sent_to = ', '.join(sorted(existing_to_emails))

            existing_cc = order.cif_mail_sent_cc or ''
            existing_cc_emails = set(e.strip().lower() for e in email_split(existing_cc) if e.strip())

            for email in cc_emails:
                if email not in existing_cc_emails:
                    existing_cc_emails.add(email)
            order.cif_mail_sent_cc = ', '.join(sorted(existing_cc_emails))

            session_id = self.env.context.get('cif_request_session_id')
            if session_id:
                session = self.env['cif.request.session'].browse(session_id)
                if session:
                    session.email_sent_to = ', '.join(to_emails) if to_emails else ''
                    session.email_sent_cc = ', '.join(cc_emails) if cc_emails else ''

        return result
