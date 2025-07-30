# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools.date_utils import get_month, get_fiscal_year
from odoo.tools.misc import format_date

import re
from collections import defaultdict
import json


class ReSequenceWizard(models.TransientModel):
    _inherit = 'account.resequence.wizard'
    
    # @api.model
    # def default_get(self, fields_list):
    #     values = super(ReSequenceWizard, self).default_get(fields_list)
    #     if 'move_ids' not in fields_list:
    #         return values
    #     active_move_ids = self.env['account.move']
    #     if self.env.context['active_model'] == 'account.move' and 'active_ids' in self.env.context:
    #         active_move_ids = self.env['account.move'].browse(self.env.context['active_ids'])
    #     if len(active_move_ids.journal_id) > 1:
    #         raise UserError(_('You can only resequence items from the same journal'))
    #     move_types = set(active_move_ids.mapped('move_type'))
    #     if (
    #         active_move_ids.journal_id.refund_sequence
    #         and ('in_refund' in move_types or 'out_refund' in move_types)
    #         and len(move_types) > 1
    #     ):
    #         raise UserError(_('The sequences of this journal are different for Invoices and Refunds but you selected some of both types.'))
    #     is_payment = set(active_move_ids.mapped(lambda x: bool(x.payment_id)))
    #     if len(is_payment) > 1:
    #         raise UserError(_('The sequences of this journal are different for Payments and non-Payments but you selected some of both types.'))
    #     values['move_ids'] = [(6, 0, active_move_ids.ids)]
    #     return values
    
    def resequence(self):
        new_values = json.loads(self.new_values)
        if self.move_ids.journal_id and self.move_ids.journal_id.restrict_mode_hash_table:
            if self.ordering == 'date':
                raise UserError(_('You can not reorder sequence by date when the journal is locked with a hash.'))
        self.env['account.move'].browse(int(k) for k in new_values.keys()).name = False
        old_states = {}
        for move_id in self.move_ids:
            old_states.update({move_id: move_id.state})
            move_id.state = 'draft'
        for move_id in self.move_ids:
            if str(move_id.id) in new_values:
                if self.ordering == 'keep':
                    move_id.name = new_values[str(move_id.id)]['new_by_name']
                else:
                    move_id.name = new_values[str(move_id.id)]['new_by_date']
                move_id.move_name = move_id.name
        for move_id in self.move_ids:
            move_id.state = old_states[move_id]
