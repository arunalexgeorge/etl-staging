# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    po_tnc = fields.Html("Terms & Conditions", default=lambda self: self.env.company.po_tnc)

    def set_values(self):
        super().set_values()
        self.company_id.po_tnc = self.po_tnc
