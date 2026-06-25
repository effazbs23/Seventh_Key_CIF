# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class InstallmentLine(models.Model):
    _inherit = 'installment.line'

    def get_installment_invoice(self):
        """Override to restrict invoice creation based on sale order state"""
        allowed_states = ('sale', 'in_cif', 'in_eoi', 'booking_sent', 'booking_signed', 'spa_sent', 'spa_signed', 'oqood_started','oqood_completed')
        if self.order_id.state not in allowed_states:
            raise UserError("An invoice can be created after the Sale Order is confirmed.")
        
        return super(InstallmentLine, self).get_installment_invoice()
