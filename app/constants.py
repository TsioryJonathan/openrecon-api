from app.categories import SHERLOCK_CATEGORIES

SHERLOCK_SITES = {
    site for sites in SHERLOCK_CATEGORIES.values() for site in sites
}
