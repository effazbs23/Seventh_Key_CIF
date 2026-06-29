# -*- coding: utf-8 -*-
{
    'name': "BS CIF Process",
    'summary': "Client Information Form (CIF) Management Process",
    'description': """
        This module handles the complete CIF (Client Information Form) workflow.

        Main Features:
        - Individual and Company CIF forms with web interfaces
        - Email OTP verification for contact information
        - Security question-based verification
        - CIF change request workflow with multi-step verification
        - CIF request session management with token-based access
        - Document upload support (Passport, Emirates ID)
        - Integration with Sale Orders and Partners

        Standalone CIF module (no seventh_key_custom dependency).
    """,
    'category': 'Sales',
    'version': '19.0.1.0.0',
    'depends': [
        'base',
        'sale',
        'contacts',
        'mail',
        'web',
        'website',
        'account',
        'sale_project',
    ],
    'data': [
        # Security
        'security/bs_cif_security.xml',
        'security/ir.model.access.csv',

        # Data & Sequences
        'data/res_partner_title_data.xml',
        'data/cif_sequence.xml',
        'data/cif_change_request_sequence.xml',
        'data/cif_request_session_sequence.xml',
        'data/email_otp_cron.xml',
        'data/cif_mail_template.xml',
        'data/cif_change_mail_template.xml',
        'data/cif_submitted_notification.xml',
        'data/cif_report_template.xml',

        # Views - Backend
        'views/cif_form_views.xml',
        'views/cif_change_request_views.xml',
        'views/cif_request_session_views.xml',
        'views/security_question_views.xml',
        'views/security_question_answer_views.xml',
        'wizards/cif_form_reject_reason_wizard_views.xml',
        'wizards/send_form_wizard_views.xml',
        'views/email_otp_views.xml',
        'views/sale_order_views.xml',
        'views/res_partner_cif_views.xml',

        # Views - Frontend/Website Templates
        'views/cif_individual_web_template.xml',
        'views/cif_company_web_template.xml',
        'views/cif_submission_templates.xml',
        'views/cif_change_verification_templates.xml',
        'views/cif_change_security_questions_template.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            '/bs_cif_process/static/src/js/cif_residency_toggle.js',
            '/bs_cif_process/static/src/js/cif_multiple_file_upload.js',
            '/bs_cif_process/static/src/js/cif_security_question_validation.js',
            '/bs_cif_process/static/src/css/cif_multiple_file_upload.css',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
