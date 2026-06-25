# -*- coding: utf-8 -*-

from odoo import models, fields


class SecurityQuestion(models.Model):
    _name = 'security.question'
    _description = 'Security Question'
    _rec_name = 'question'

    question = fields.Char(string='Question')
    ans_max_length = fields.Integer(string='Maximum Length(Character) of Answer', default=255)
