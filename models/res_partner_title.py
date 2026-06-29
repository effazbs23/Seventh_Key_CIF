# -*- coding: utf-8 -*-

from odoo import models, fields

class ResPartnerTitle(models.Model):
    _name = 'res.partner.title'
    _description = 'Contact Title'
    _order = 'name'

    name = fields.Char(string='Title', required=True, translate=True)
    shortcut = fields.Char(string='Abbreviation', translate=True)
