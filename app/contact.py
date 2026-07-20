"""Contact / social link helpers (shared standard across the appchen apps).

Turns the CONTACT_* config into the list of links to render (only the channels
an operator actually configured), and splits an email address so no literal
address - and no ``mailto:`` - ever appears in the page source. The client
reassembles the address (see the ``js-mail`` handler in base.html), which
defeats the naive harvesters that scrape pages for ``\\S+@\\S+`` or ``mailto:``
links.
"""

_SCHEMES = ('http://', 'https://')


def _as_url(value: str, base: str) -> str:
    """A full URL is used as-is; anything else is treated as a username that
    hangs off ``base`` (so operators can set either)."""
    value = value.strip()
    if value.startswith(_SCHEMES):
        return value
    return base + value.lstrip('@/')


def get_contact_links(config) -> list:
    """``[{key, label, icon, fa_icon, url, rel}]`` for every configured channel.

    Order is fixed; channels with no value are omitted, so the footer shows
    exactly what the operator opted into. ``icon`` is a Bootstrap Icons name
    and ``fa_icon`` the Font Awesome equivalent, so the same helper serves
    appchen apps on either icon set - templates pick whichever they load.
    """
    links = []

    mastodon = (config.get('CONTACT_MASTODON') or '').strip()
    if mastodon:
        links.append({
            'key': 'mastodon', 'label': 'Mastodon', 'icon': 'bi-mastodon', 'fa_icon': 'fab fa-mastodon',
            # A full profile URL is expected. rel="me" lets Mastodon verify
            # this link as belonging back to that profile.
            'url': mastodon,
            'rel': 'me noopener noreferrer',
        })

    github = (config.get('CONTACT_GITHUB') or '').strip()
    if github:
        links.append({
            'key': 'github', 'label': 'GitHub', 'icon': 'bi-github', 'fa_icon': 'fab fa-github',
            'url': _as_url(github, 'https://github.com/'),
            'rel': 'noopener noreferrer',
        })

    kofi = (config.get('CONTACT_KOFI') or '').strip()
    if kofi:
        links.append({
            'key': 'kofi', 'label': 'Ko-fi', 'icon': 'bi-cup-straw', 'fa_icon': 'fas fa-mug-hot',
            'url': _as_url(kofi, 'https://ko-fi.com/'),
            'rel': 'noopener noreferrer',
        })

    bmc = (config.get('CONTACT_BUYMEACOFFEE') or '').strip()
    if bmc:
        links.append({
            'key': 'buymeacoffee', 'label': 'Buy Me a Coffee', 'icon': 'bi-cup-hot', 'fa_icon': 'fas fa-coffee',
            'url': _as_url(bmc, 'https://www.buymeacoffee.com/'),
            'rel': 'noopener noreferrer',
        })

    return links


def split_email(email: str):
    """``(user, domain)`` for a valid address, else ``None``.

    Templates render these two parts separately (never joined with ``@``); the
    client rebuilds the real address and the ``mailto:`` link.
    """
    email = (email or '').strip()
    if email.count('@') != 1:
        return None
    user, _, domain = email.partition('@')
    if user and domain:
        return (user, domain)
    return None


def legal_globals(config) -> dict:
    """Template globals for the footer and legal pages, computed from config.

    Registered as a context processor so every page (all extend base.html, which
    renders the shared footer) has these available. Kept as a plain function so
    both the app factory and the test harness can wire it up identically.
    """
    return {
        'contact_links': get_contact_links(config),
        'contact_email': split_email(config.get('CONTACT_EMAIL', '')),
        'imprint_email': split_email(config.get('IMPRINT_EMAIL', '')),
        'imprint_enabled': config.get('IMPRINT_ENABLED', False),
        # Commercial-licensing contact, split so no literal address appears in
        # the page source; the client reassembles it like the others.
        'license_email': split_email('appchen@outlook.at'),
    }
