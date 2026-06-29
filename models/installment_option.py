# -*- coding: utf-8 -*-

from odoo import models, fields


class InstallmentOption(models.Model):
    _name = 'installment.option'
    _description = 'Installment Option'
    _rec_name = 'name'

    name = fields.Char(string='Name', required=True)
    dld_fees_percentage = fields.Float(string='DLD Fees Percentage', default=0.0)
    dld_fees_add_amount = fields.Float(string='DLD Fees Additional Amount', default=0.0)
