# -*- coding: utf-8 -*-

from odoo import models, fields


class SaleOrderPurchaser(models.Model):
    _name = 'sale.order.purchaser'
    _description = 'Sale Order Purchaser'
    _rec_name = 'partner_id'
    _order = 'sequence, id'

    sequence = fields.Integer(string='Sequence', default=10)
    sale_order_id = fields.Many2one('sale.order', string='Sale Order', required=True, ondelete='cascade', index=True)
    partner_id = fields.Many2one('res.partner', string='Purchaser', ondelete='restrict', index=True)
    share_percentage = fields.Float(string='Share Percentage', default=0.0)

    # CIF linkage
    cif_form_id = fields.Many2one(
        'cif.form',
        string='CIF Form',
        readonly=True,
        copy=False,
        help='CIF form submitted by this purchaser'
    )
