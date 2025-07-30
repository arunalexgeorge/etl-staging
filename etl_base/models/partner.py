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

from base64 import b64encode
from hashlib import sha512
from odoo import models, fields, api
from odoo.tools import html_escape, file_open
from odoo.exceptions import UserError, ValidationError
import logging
logger = logging.getLogger(__name__)
import re

def get_hsl_from_seed(seed):
    hashed_seed = sha512(seed.encode()).hexdigest()
    # full range of colors, in degree
    hue = int(hashed_seed[0:2], 16) * 360 / 255
    # colorful result but not too flashy, in percent
    sat = int(hashed_seed[2:4], 16) * ((70 - 40) / 255) + 40
    # not too bright and not too dark, in percent
    lig = 45
    return f'hsl({hue:.0f}, {sat:.0f}%, {lig:.0f}%)'

class AvatarMixin(models.AbstractModel):
    _inherit = 'avatar.mixin'
    
    avatar_1920 = fields.Image("Avatar", compute="_compute_avatar_1920")
    avatar_1024 = fields.Image("Avatar 1024", compute="_compute_avatar_1024")
    avatar_512 = fields.Image("Avatar 512", compute="_compute_avatar_512")
    avatar_256 = fields.Image("Avatar 256", compute="_compute_avatar_256")
    avatar_128 = fields.Image("Avatar 128", compute="_compute_avatar_128")
    
    @api.depends(lambda self: [self._avatar_name_field, 'image_1920'])
    def _compute_avatar_1920(self):
        self._compute_avatar('avatar_1920', 'image_1920')

    @api.depends(lambda self: [self._avatar_name_field, 'image_1024'])
    def _compute_avatar_1024(self):
        self._compute_avatar('avatar_1024', 'image_1024')

    @api.depends(lambda self: [self._avatar_name_field, 'image_512'])
    def _compute_avatar_512(self):
        self._compute_avatar('avatar_512', 'image_512')

    @api.depends(lambda self: [self._avatar_name_field, 'image_256'])
    def _compute_avatar_256(self):
        self._compute_avatar('avatar_256', 'image_256')

    @api.depends(lambda self: [self._avatar_name_field, 'image_128'])
    def _compute_avatar_128(self):
        self._compute_avatar('avatar_128', 'image_128')
        
    def _compute_avatar1(self, avatar_field, image_field):
        for record in self:
            avatar = record._avatar_generate_svg()
            record[avatar_field] = avatar
    
    def _compute_avatar(self, avatar_field, image_field):
        for record in self:
            avatar = record[image_field]
            if not avatar:
                if record.id and record[record._avatar_name_field]:
                    avatar = record._avatar_generate_svg()
                else:
                    avatar = b64encode(record._avatar_get_placeholder())
            record[avatar_field] = avatar
            
    def _avatar_generate_svg(self):
        full_name = self[self._avatar_name_field]
        name_split = full_name.split(' ')
        if len(name_split) == 1:
            name = full_name[:3]
        elif len(name_split) > 1:
            name = name_split[0][0] + name_split[1][0]
        initial = html_escape(name.upper())
        # logger.info('*'*75)
        # logger.info(initial)
        bgcolor = get_hsl_from_seed(self[self._avatar_name_field] + str(self.create_date.timestamp() if self.create_date else ""))
        # logger.info(bgcolor)
        # logger.info('#'*75)
        return b64encode((
            "<?xml version='1.0' encoding='UTF-8' ?>"
            "<svg height='180' width='180' xmlns='http://www.w3.org/2000/svg' xmlns:xlink='http://www.w3.org/1999/xlink'>"
            f"<rect fill='{bgcolor}' height='180' width='180'/>"
            f"<text fill='#ffffff' font-size='96' text-anchor='middle' x='90' y='125' font-family='sans-serif'>{initial}</text>"
            "</svg>"
        ).encode())

class PartnerBank(models.Model):
    _inherit = 'res.partner.bank'
    
    ifsc_code = fields.Char('IFSC Code')

class SalesRegion(models.Model):
    _name = 'sales.region'
    _description = 'Sales Region'
    
    name = fields.Char('Region')

class Groups(models.Model):
    _inherit = 'res.groups'
    _order = 'sequence'
    
    sequence = fields.Integer('Sequence')
        
class Partner(models.Model):
    _inherit = 'res.partner'
    
    partner_type = fields.Selection([
        ('customer', 'Customer (Domestic)'),
        ('customer_exp', 'Customer (Export)'), 
        ('vendor', 'Vendor (Domestic)'),
        ('vendor_for', 'Vendor (Foreign)'),
        ('employee', 'Employee'),
        ], 'Contact Type', required=True)
    partner_code = fields.Char('Partner Code', copy=False)
    sales_executive_id = fields.Many2one('hr.employee', 'Sales Executive')
    zonal_head_id = fields.Many2one('hr.employee', 'Zonal Head')
    region_id = fields.Many2one('sales.region', 'Region')
    sfa_code = fields.Char('SFA Code', copy=False)
    aadhar_no = fields.Char('Aadhar Number')
    tcs_ok = fields.Boolean('TCS Applicable')
    tag_id = fields.Many2one('crm.tag', 'Tag')
    invoice_decimal = fields.Integer('DP', default=2)
    login_user_id = fields.Many2one('res.users', compute='_login_user')
     
    def _login_user(self):
        for user in self:
            user.login_user_id = self.env.user.user_access and self.env.user.id or False
    
    def _get_name(self):
        """ Utility method to allow name_get to be overrided without re-browse the partner """
        partner = self
        name = partner.name or ''

        if partner.company_name or partner.parent_id:
            if not name and partner.type in ['invoice', 'delivery', 'other']:
                name = dict(self.fields_get(['type'])['type']['selection'])[partner.type]
            if not partner.is_company:
                name = self._get_contact_name(partner, name)
        if partner.city and self._context.get('show_city'):
            name = '%s [%s]'%(name, partner.city)
        if self._context.get('show_address_only'):
            name = partner._display_address(without_company=True)
        if self._context.get('show_address'):
            name = name + "\n" + partner._display_address(without_company=True)
        name = re.sub(r'\s+\n', '\n', name)
        if self._context.get('partner_show_db_id'):
            name = "%s (%s)" % (name, partner.id)
        if self._context.get('address_inline'):
            splitted_names = name.split("\n")
            name = ", ".join([n for n in splitted_names if n.strip()])
        if self._context.get('show_email') and partner.email:
            name = "%s <%s>" % (name, partner.email)
        if self._context.get('html_format'):
            name = name.replace('\n', '<br/>')
        if self._context.get('show_vat') and partner.vat:
            name = "%s ‒ %s" % (name, partner.vat)
        return name.strip()
    
    def update_partner_code(self):
        partners = self.search([
            ('partner_code', 'ilike', 'EM'),
            '|', ('active', '=', True), ('active', '=', False)
            ], order='partner_code')
        for partner in partners:
            number = int(partner.partner_code[2:])
            partner.partner_code = 'EM' + str(number).zfill(4)
            partner.partner_type = 'employee'
        return True
    
    @api.model_create_multi
    def create(self, vals_list):
        seq_dic = {
            'customer': 'CD',
            'customer_exp': 'CE',
            'vendor': 'VD',
            'vendor_for': 'VF',
            'employee': 'EM'
            }
        for val in vals_list:
            if not 'partner_code' in val:
                partner_type = val.get('partner_type', '')
                if partner_type in ('customer', 'customer_exp', 'vendor', 'vendor_for', 'employee'):
                    padding = 5
                    if val['partner_type'] == 'employee':
                        padding = 4
                    partners = self.search([
                        ('partner_type', '=', partner_type),
                        '|', ('active', '=', True), ('active', '=', False),
                        ('partner_code', '!=', False)
                        ], order='partner_code desc', limit=1)
                    if partners and partners[0].partner_code:
                        next_number = int(partners[0].partner_code[2:])+1
                    else:
                        next_number = 1
                    val['partner_code'] = seq_dic[partner_type] + str(next_number).zfill(padding)
        return super(Partner, self).create(vals_list)
    
    