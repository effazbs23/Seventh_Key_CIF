# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class InstallmentLine(models.Model):
    _name = 'installment.line'
    _description = 'Installment Line'
    _rec_name = 'name'

    name = fields.Char(string='Description', required=True)
    order_id = fields.Many2one('sale.order', string='Sale Order', required=True, ondelete='cascade', index=True)
    partner_id = fields.Many2one('res.partner', related='order_id.partner_id', string='Customer', readonly=True)
    line_type = fields.Selection([
        ('downpayment', 'Down Payment'),
        ('admin_fees', 'Admin Fees'),
        ('dld_fees', 'DLD Fees'),
        ('installment', 'Installment'),
    ], string='Type', required=True, default='installment')
    installment_percentage = fields.Float(string='Percentage (%)', default=0.0)
    amount = fields.Monetary(string='Amount', currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', related='order_id.currency_id', string='Currency')
    invoice_ids = fields.One2many('account.move', 'invoice_line_ids', string='Invoices')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('paid', 'Paid'),
        ('cancel', 'Cancelled'),
    ], string='Status', default='draft')

    def get_installment_invoice(self):
        """Override to restrict invoice creation based on sale order state"""
        allowed_states = ('sale', 'in_cif', 'in_eoi', 'booking_sent', 'booking_signed', 'spa_sent', 'spa_signed', 'oqood_started','oqood_completed')
        if self.order_id.state not in allowed_states:
            raise UserError("An invoice can be created after the Sale Order is confirmed.")
        return super(InstallmentLine, self).get_installment_invoice()
