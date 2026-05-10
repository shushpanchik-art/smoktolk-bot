from . import start, profile, gifts, catalog, referral, rules, verify, admin, _admin_addon

ROUTERS = [
    start.router, profile.router, gifts.router, catalog.router,
    referral.router, rules.router, verify.router, admin.router,
    _admin_addon.router,
]
