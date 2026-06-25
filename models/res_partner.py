# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class ResPartner(models.Model):
    """Extend res.partner with CIF form count and navigation."""

    _inherit = 'res.partner'

    cif_form_count = fields.Integer(
        string='CIF Forms',
        compute='_compute_cif_form_count',
        store=False,
    )

    @api.depends('user_id')
    def _compute_cif_form_count(self):
        for partner in self:
            partner.cif_form_count = self.env['cif.form'].search_count([
                ('created_partner_id', '=', partner.id)
            ])

    def action_view_cif_forms(self):
        """Open CIF forms linked to this partner via smart button."""
        self.ensure_one()
        cif_forms = self.env['cif.form'].search([
            ('created_partner_id', '=', self.id)
        ])

        if not cif_forms:
            raise UserError(_("No CIF forms found for this partner."))

        if len(cif_forms) == 1:
            return {
                'name': _('Client Information Form'),
                'type': 'ir.actions.act_window',
                'res_model': 'cif.form',
                'view_mode': 'form',
                'res_id': cif_forms.id,
                'target': 'current',
            }

        return {
            'name': _('Client Information Forms'),
            'type': 'ir.actions.act_window',
            'res_model': 'cif.form',
            'view_mode': 'list,form',
            'domain': [('created_partner_id', '=', self.id)],
            'target': 'current',
        }

