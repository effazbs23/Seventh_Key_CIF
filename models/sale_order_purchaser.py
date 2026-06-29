# -*- coding: utf-8 -*-

from odoo import models, fields, api


class SaleOrderPurchaser(models.Model):
    _name = 'sale.order.purchaser'
    _description = 'Sale Order Purchaser'
    _rec_name = 'partner_id'
    _order = 'sequence, id'

    sequence = fields.Integer(string='Sequence', default=10)
    sale_order_id = fields.Many2one('sale.order', string='Sale Order', required=True, ondelete='cascade', index=True)
    partner_id = fields.Many2one('res.partner', string='Purchaser', ondelete='restrict', index=True)

    partner_email = fields.Char(string='Email', related='partner_id.email', readonly=True)
    partner_mobile = fields.Char(string='Mobile', related='partner_id.mobile', readonly=True)
    partner_passport_no = fields.Char(string='Passport No', related='partner_id.passport_no', readonly=True)
    partner_nationality_id = fields.Many2one('res.country', string='Nationality', related='partner_id.nationality', readonly=True)
    partner_contact_address = fields.Char(string='Contact Address', related='partner_id.contact_address', readonly=True)

    share_percentage = fields.Float(string='Share Percentage', default=0.0)
    is_representative = fields.Boolean(string='Representative', default=False)

    # EOI linkage (kept for backward compatibility)
    eoi_signed = fields.Boolean(string='EOI Signed', default=False)

    # CIF linkage
    cif_form_id = fields.Many2one(
        'cif.form',
        string='CIF Form',
        readonly=True,
        copy=False,
        help='CIF form submitted by this purchaser'
    )

    def action_set_representative(self):
        self.ensure_one()
        order = self.sale_order_id
        order.partner_id = self.partner_id
        order.write({'partner_id': self.partner_id.id})
        order.sudo().message_post(
            body=f"Representative set to: {self.partner_id.display_name}",
            subject="Representative Updated"
        )
        order.sale_order_purchaser_ids.write({'is_representative': False})
        self.is_representative = True

    def action_open_activity_wizard(self):
        self.ensure_one()
        return {
            'name': 'Activity',
            'type': 'ir.actions.act_window',
            'res_model': 'mail.activity',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_res_id': self.id,
                'default_res_model': 'sale.order.purchaser',
            },
        }
