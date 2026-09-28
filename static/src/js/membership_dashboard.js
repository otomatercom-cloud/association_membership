/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

// NOTE: all counting/summing happens server-side (see
// models/dashboard.py get_dashboard_data) and is returned as one plain
// dict from a single RPC call. We deliberately do NOT use the ORM
// service's read_group/readGroup here - Odoo 19 renamed it to
// formattedReadGroup with a different result shape (a real breaking
// change confirmed against core source), and since the server already
// does the aggregation, there is no need to touch that API at all.
export class MembershipDashboard extends Component {
    static template = "association_membership.MembershipDashboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.state = useState({
            loading: true,
            data: null,
        });
        onWillStart(async () => {
            this.state.data = await this.orm.call(
                "association.membership.dashboard",
                "get_dashboard_data",
                []
            );
            this.state.loading = false;
        });
    }

    formatCurrency(value) {
        const amount = (value || 0).toLocaleString(undefined, {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });
        const symbol = this.state.data.currency_symbol || "";
        if (this.state.data.currency_position === "after") {
            return `${amount} ${symbol}`;
        }
        return `${symbol} ${amount}`;
    }

    typeBarWidth(count) {
        const total = this.state.data.total_members || 1;
        return `${Math.max(2, (count / total) * 100).toFixed(1)}%`;
    }

    typePercent(count) {
        const total = this.state.data.total_members || 1;
        return ` (${((count / total) * 100).toFixed(0)}%)`;
    }

    openMembers(domain) {
        this.actionService.doAction({
            type: "ir.actions.act_window",
            name: "Members",
            res_model: "association.member",
            views: [[false, "list"], [false, "form"]],
            domain: domain || [],
            target: "current",
        });
    }

    openApplications(domain) {
        this.actionService.doAction({
            type: "ir.actions.act_window",
            name: "Applications",
            res_model: "association.membership.application",
            views: [[false, "list"], [false, "form"]],
            domain: domain || [],
            target: "current",
        });
    }

    openPayments(domain) {
        this.actionService.doAction({
            type: "ir.actions.act_window",
            name: "Payments",
            res_model: "association.membership.payment",
            views: [[false, "list"], [false, "form"]],
            domain: domain || [],
            target: "current",
        });
    }
}

registry.category("actions").add("association_membership_dashboard", MembershipDashboard);
