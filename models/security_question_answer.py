# -*- coding: utf-8 -*-

from odoo import models, fields


class SecurityQuestionAnswer(models.Model):
    _name = 'security.question.answer'
    _description = 'Security Question Answer'
    _order = 'sequence, id'

    sequence = fields.Integer(string='Sequence', default=10)
    partner_id = fields.Many2one('res.partner', string='Partner', ondelete='cascade', index=True)
    question_id = fields.Many2one('security.question', string='Security Question', required=True)
    answer = fields.Char(string='Answer', required=True)
    cif_form_id = fields.Many2one('cif.form', string='CIF Form', ondelete='cascade', index=True)
