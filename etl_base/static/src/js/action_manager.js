/** @odoo-module **/
import { ActionContainer } from "@web/webclient/actions/action_container"
import { Component, xml, onWillDestroy } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
var ajax = require("web.ajax");

patch(ActionContainer.prototype, "field_highlight", {
    setup() {
        this.info = {};
        this.onActionManagerUpdate = ({ detail: info }) => {
            this.info = info;
            this.render();
            var list=[]
            ajax.jsonRpc('/mandatory/config_params', 'call', {
            }).then(function (data) {
                for (let x in data) {
                list.push(data[x]);
                }
                 const root = document.documentElement;
                 root.style.setProperty('--margin-bottom-color',list[0]);
            });
        };
        this.env.bus.addEventListener("ACTION_MANAGER:UPDATE",
        this.onActionManagerUpdate);
        onWillDestroy(() => {
            this.env.bus.removeEventListener("ACTION_MANAGER:UPDATE",
            this.onActionManagerUpdate);
        });
    }
});