# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class CIFFormRejectReasonWizard(models.TransientModel):
    _name = 'cif.form.reject.reason.wizard'
    _description = 'CIF Form Reject Reason Wizard'

    cif_form_id = fields.Many2one('cif.form', string='CIF Form', required=True, readonly=True)
    reason = fields.Text(string='Reason', required=True)

    def action_confirm_reject(self):
        self.ensure_one()
        if not self.cif_form_id:
            raise UserError(_('No CIF form found to reject.'))
        return self.cif_form_id.action_reject_with_reason(self.reason)
