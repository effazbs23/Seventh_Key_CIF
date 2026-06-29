# -*- coding: utf-8 -*-

from odoo import models, fields


class EoiRequestSession(models.Model):
    _name = 'eoi.request.session'
    _description = 'EOI Request Session'
    _rec_name = 'sale_order_id'

    sale_order_id = fields.Many2one('sale.order', string='Sale Order', required=True, ondelete='cascade', index=True)
    eoi_token = fields.Char(string='EOI Token', copy=False)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('submitted', 'Submitted'),
        ('expired', 'Expired'),
    ], string='Status', default='draft')
    allowed_submissions = fields.Integer(string='Allowed Submissions', default=1)
