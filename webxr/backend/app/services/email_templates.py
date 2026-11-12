from html import escape


def _security_email(
    *,
    title: str,
    preheader: str,
    introduction: str,
    reassurance: str,
    button_label: str,
    action_url: str,
    expiry_copy: str,
) -> str:
    safe_url = escape(action_url, quote=True)
    return f'''<!doctype html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)}</title>
<!--[if !mso]><!--><link href="https://assets-maas-platform.s3-eu-central-1.amazonaws.com/static/mails/fonts/stylesheet.css" rel="stylesheet" type="text/css"><style type="text/css">@import url(https://assets-maas-platform.s3-eu-central-1.amazonaws.com/static/mails/fonts/stylesheet.css);</style><!--<![endif]-->
<style>
@media only screen and (max-width:520px) {{ .email-shell {{ width:100% !important; }} .email-pad {{ padding-left:24px !important;padding-right:24px !important; }} }}
</style></head>
<body style="margin:0;padding:0;word-spacing:normal;background:#fff;-webkit-text-size-adjust:100%;">
<div style="display:none;font-size:1px;color:#fff;line-height:1px;max-height:0;max-width:0;opacity:0;overflow:hidden;">{escape(preheader)}</div>
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"><tr><td align="center" style="padding:2% 0;">
<table class="email-shell" role="presentation" width="520" cellspacing="0" cellpadding="0" border="0" style="width:100%;max-width:520px;"><tr><td class="email-pad" style="padding:0 6.5%;font-family:Mirage,-apple-system,BlinkMacSystemFont,Helvetica,Arial,sans-serif;color:#000;">
<div style="height:12px;line-height:12px;font-size:0">&nbsp;</div>
<div style="padding:0 0 6%;font-size:18px;font-weight:450;line-height:140%;color:#000000;">Cyclone</div>
<div style="height:32px;line-height:32px;font-size:0">&nbsp;</div>
<div style="padding:0 0 6%;font-size:18px;font-weight:450;line-height:140%;">{escape(introduction)}</div>
<div style="padding:0 0 6%;font-size:18px;font-weight:450;line-height:140%;">{escape(reassurance)}</div>
<table role="presentation" cellspacing="0" cellpadding="0" border="0" style="border-collapse:separate;line-height:100%;"><tr><td align="center" bgcolor="#0a0a0a" style="border-radius:18px;background:#0a0a0a;mso-padding-alt:20px 24px;"><a href="{safe_url}" target="_blank" style="display:inline-block;background:#0a0a0a;color:#F5F5F5;font-family:Mirage,-apple-system,BlinkMacSystemFont,Helvetica,Arial,sans-serif;font-size:16px;font-weight:450;line-height:1;text-decoration:none;padding:20px 24px;border-radius:18px;">{escape(button_label)}</a></td></tr></table>
<div style="height:16px;line-height:16px;font-size:0">&nbsp;</div>
<div style="padding:0 0 6%;font-size:12px;font-weight:400;line-height:140%;">{escape(expiry_copy)}</div>
<div style="height:48px;line-height:48px;font-size:0">&nbsp;</div>
<div style="padding:0 0 6%;font-size:18px;font-weight:450;line-height:140%;color:#000000;">Regards,<br>Cyclone</div>
<div style="height:32px;line-height:32px;font-size:0">&nbsp;</div>
<div style="font-size:12px;font-weight:400;line-height:140%;color:#999;">Cyclone account security notification.</div>
</td></tr></table></td></tr></table></body></html>'''


def password_reset_email(reset_url: str, expires_minutes: int) -> str:
    return _security_email(
        title="Reset your Reality to 3D password",
        preheader="Use the secure link to choose a new password for your Reality to 3D account.",
        introduction="Hi there, we received a request to reset your Reality to 3D password. Use the button below to choose a new one.",
        reassurance="If you didn’t request this change, you can ignore this email. Your password will remain unchanged.",
        button_label="Reset password",
        action_url=reset_url,
        expiry_copy=f"This link will expire in {expires_minutes} minutes.",
    )


def verification_email(verification_url: str, expires_minutes: int) -> str:
    return _security_email(
        title="Verify your Cyclone account",
        preheader="Verify your email address to finish creating your Cyclone account.",
        introduction="Welcome to Cyclone. Verify your email address using the button below to finish creating your account.",
        reassurance="If you didn’t create this account, you can ignore this email.",
        button_label="Verify email address",
        action_url=verification_url,
        expiry_copy=f"This link will expire in {expires_minutes} minutes.",
    )
