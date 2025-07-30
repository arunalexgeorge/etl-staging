# -*- coding: utf-8 -*-
#############################################################################
#
#    Steigend IT Solutions.
#
#    Copyright (C) 2023-TODAY Steigend IT Solutions.
#
#    You can modify it under the terms of the GNU AFFERO
#    GENERAL PUBLIC LICENSE (AGPL v3), Version 3.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU AFFERO GENERAL PUBLIC LICENSE (AGPL v3) for more details.
#
#    You should have received a copy of the GNU AFFERO GENERAL PUBLIC LICENSE
#    (AGPL v3) along with this program.
#    If not, see <http://www.gnu.org/licenses/>.
#
#############################################################################

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare
from cgitb import reset

class AccountMove(models.Model):
    _inherit = 'account.move'
    
    @api.model
    def _search(self, args, offset=0, limit=None, order=None, count=False, access_rights_uid=None):
        args = args or []
        user = self.env.user
        if 'no_filter' in self._context:
            pass
        else:
            branch_ids = self._context.get('allowed_branch_ids', user.branch_ids.ids)
            args += ['|', ('branch_id', '=', False), ('branch_id', 'in', branch_ids)]
        return super(AccountMove, self)._search(args, offset, limit, order, count=count, access_rights_uid=access_rights_uid)
    
    @api.model
    def _read_group_raw(self, domain, fields, groupby, offset=0, limit=None, orderby=False, lazy=True):
        domain = domain or []
        user = self.env.user
        if 'no_filter' in self._context:
            pass
        else:
            branch_ids = self._context.get('allowed_branch_ids', user.branch_ids.ids)
            domain += ['|', ('branch_id', '=', False), ('branch_id', 'in', branch_ids)]
        return super(AccountMove, self)._read_group_raw(domain, fields, groupby, offset=offset, limit=limit, orderby=orderby, lazy=lazy)
    
    @api.model
    def default_get(self, default_fields):
        res = super(AccountMove, self).default_get(default_fields)
        branch_id = False
        if self._context.get('branch_id'):
            branch_id = self._context.get('branch_id')
        elif self.env.user.branch_id:
            branch_id = self.env.user.branch_id.id
        res.update({'branch_id' : branch_id})
        return res
    
    branch_id = fields.Many2one('res.branch', "Branch")
    
class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'
    
    def correct_moveline_data(self):
        if self.account_id.id == 5649:
            mtv_obj = self.env['mail.tracking.value']
            mtvs = mtv_obj.search([
                ('new_value_integer', '=', 5649),
                ('mail_message_id.res_id', '=', self.move_id.id)
                ])
            old_account_id = mtvs[0].old_value_integer
            old_acc_code = self.env['account.account'].browse(old_account_id).code
            acc_emp_dic = {'105004001': 'EM0005', '105004065': 'EM0006', '105004003': 'EM0013', '105004004': 'EM0015', '105004070': 'EM0016', '105004071': 'EM0018', '105004005': 'EM0020', '105004007': 'EM0022', '105004008': 'EM0023', '105004010': 'EM0025', '105004073': 'EM0027', '105004011': 'EM0029', '105004066': 'EM0031', '105004013': 'EM0033', '105004074': 'EM0035', '105004068': 'EM0036', '105004014': 'EM0037', '105004016': 'EM0041', '105004019': 'EM0044', '105004021': 'EM0046', '105004022': 'EM0047', '105004023': 'EM0048', '105004025': 'EM0050', '105004027': 'EM0053', '105004028': 'EM0054', '105004031': 'EM0056', '105004032': 'EM0062', '105004082': 'EM0063', '105004084': 'EM0064', '105004067': 'EM0071', '105004034': 'EM0072', '105004035': 'EM0074', '105004036': 'EM0076', '105004083': 'EM0078', '105004037': 'EM0079', '105004038': 'EM0080', '105004039': 'EM0081', '105004040': 'EM0082', '105004042': 'EM0085', '105004043': 'EM0086', '105004044': 'EM0087', '105004045': 'EM0088', '105004069': 'EM0089', '105004072': 'EM0091', '105004047': 'EM0092', '105004048': 'EM0094', '105004049': 'EM0095', '105004050': 'EM0096', '105004051': 'EM0097', '105004053': 'EM0098', '105004054': 'EM0099', '105004055': 'EM0100', '105004056': 'EM0103', '105004058': 'EM0106', '105004059': 'EM0107', '105004046': 'EM0109', '105004062': 'EM0110', '105004063': 'EM0111', '105004030': 'EM0112'}
            if old_acc_code in acc_emp_dic:
                partner = self.env['res.partner'].search([('partner_code', '=', acc_emp_dic[old_acc_code])])
                if partner:
                    self.partner_id = partner.id
        return True
    
    @api.model
    def _search(self, args, offset=0, limit=None, order=None, count=False, access_rights_uid=None):
        if 'payment_matching' in self._context:
            order = 'date'
        args = args or []
        user = self.env.user
        
        if 'no_filter' in self._context or self._context.get('tree_view_ref', '') == 'account_accountant.view_account_move_line_list_bank_rec_widget':
            pass
        else:
            branch_ids = self._context.get('allowed_branch_ids', user.branch_ids.ids)
            args += ['|', ('branch_id', '=', False), ('branch_id', 'in', branch_ids)]
        return super(AccountMoveLine, self)._search(args, offset, limit, order, count=count, access_rights_uid=access_rights_uid)
    
    @api.model
    def _read_group_raw(self, domain, fields, groupby, offset=0, limit=None, orderby=False, lazy=True):
        domain = domain or []
        user = self.env.user
        if 'no_filter' in self._context:
            pass
        else:
            branch_ids = self._context.get('allowed_branch_ids', user.branch_ids.ids)
            domain += ['|', ('branch_id', '=', False), ('branch_id', 'in', branch_ids)]
        return super(AccountMoveLine, self)._read_group_raw(domain, fields, groupby, offset=offset, limit=limit, orderby=orderby, lazy=lazy)
    
    @api.depends('move_id', 'move_id.branch_id', 'move_id.state')
    def _compute_branch(self):
        for line in self:
            line.branch_id = line.move_id and line.move_id.branch_id.id or False 
        
    branch_id = fields.Many2one('res.branch', "Branch", compute='_compute_branch', store=True)
