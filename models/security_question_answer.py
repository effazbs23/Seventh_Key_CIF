# -*- coding: utf-8 -*-

from odoo import models, fields


class SecurityQuestionAnswer(models.Model):

    _inherit = 'security.question.answer'

    cif_form_id = fields.Many2one('cif.form', string='CIF Form', ondelete='cascade', index=True)


