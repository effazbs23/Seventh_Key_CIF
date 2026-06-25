# -*- coding: utf-8 -*-
"""
CIF Process - Sale Order Purchaser Extensions

This module extends the sale.order.purchaser model with CIF-related fields.
CIF (Client Information Form) fields are defined here instead of in seventh_key_custom
to maintain clean module hierarchy.
"""

from odoo import models, fields


class SaleOrderPurchaser(models.Model):
    """Extend sale.order.purchaser with CIF form linkage."""

    _inherit = 'sale.order.purchaser'

    # CIF linkage for this purchaser slot
    cif_form_id = fields.Many2one(
        'cif.form',
        string='CIF Form',
        readonly=True,
        copy=False,
        help='CIF form submitted by this purchaser'
    )
