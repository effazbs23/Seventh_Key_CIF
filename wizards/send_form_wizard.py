# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class SendFormWizard(models.TransientModel):
    _name = 'send.form.wizard'
    _description = 'Wizard to select customer type before sending a form'

    customer_type = fields.Selection(
        string='Customer Type',
        selection=[('person', 'Individual'), ('company', 'Company')],
        required=True,
        help="Select the customer type to correctly format the document."
    )
    form_type = fields.Selection(
        [('booking', 'Booking Form'), ('spa', 'SPA Form'), ('cif', 'CIF Form')],
        string="Form Type",
        readonly=True
    )

    purchasers_count = fields.Integer(string='Members Count', default=1)

    def action_proceed(self):
        self.ensure_one()
        active_id = self.env.context.get('active_id')
        active_model = self.env.context.get('active_model')

        if active_model == 'sale.order' and active_id:
            sale_order = self.env['sale.order'].browse(active_id)

            if self.form_type == 'cif':
                if not self.purchasers_count or self.purchasers_count <= 0:
                    raise ValidationError(_('Members Count must be greater than zero.'))
                return sale_order.action_send_cif_form(
                    self.customer_type,
                    allowed_submissions=self.purchasers_count
                )

        return {'type': 'ir.actions.act_window_close'}
