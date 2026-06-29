# -*- coding: utf-8 -*-

from odoo import models, fields


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    amount_in_additional_currency = fields.Monetary(
        string='Amount in Alt. Currency',
        currency_field='additional_currency_id',
        compute='_compute_amount_in_additional_currency',
        store=False,
    )
    additional_currency_id = fields.Many2one(
        'res.currency',
        related='order_id.additional_currency_id',
        string='Additional Currency',
    )

    discount_total = fields.Monetary(
        string='Discount Total',
        currency_field='currency_id',
        compute='_compute_discount_total',
        store=False,
    )

    def _compute_amount_in_additional_currency(self):
        for line in self:
            if line.order_id.additional_currency_id and line.order_id.currency_id:
                rate = line.order_id.currency_id.rate or 1.0
                line.amount_in_additional_currency = line.price_subtotal * rate
            else:
                line.amount_in_additional_currency = 0.0

    def _compute_discount_total(self):
        for line in self:
            line.discount_total = line.price_unit * line.product_uom_qty * (line.discount / 100.0)
