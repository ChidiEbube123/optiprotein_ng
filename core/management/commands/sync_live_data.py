import os
import time

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import Corridor
from core.live_data import (CORRIDOR_COORDS, download, norm_state, osm_outlets, parse_nbs_beef)
from core.live_data import (CORRIDOR_COORDS, beef_price_for_state, download, osm_outlets, parse_nbs_beef)
# OSM undercounts informal food outlets in Nigeria. Leave at 1.0 (honest floor) unless you
# have ground-truth counts for a corridor to calibrate against.
OSM_FACTOR = float(os.environ.get("OSM_UNDERCOUNT_FACTOR", "1.0"))


class Command(BaseCommand):
    help = "Refresh corridors with real data: NBS beef prices + OpenStreetMap outlet counts."

    def add_arguments(self, p):
        p.add_argument("--nbs-file", help="Path to a downloaded NBS Selected Food Price Watch .xlsx/.xls/.csv")
        p.add_argument("--nbs-url", help="Direct link to that file (copy it from nigerianstat.gov.ng)")
        p.add_argument("--skip-osm", action="store_true")
        p.add_argument("--radius", type=int, default=2000, help="OSM search radius in metres")
        p.add_argument("--dry-run", action="store_true", help="Print what would change; save nothing")

    def handle(self, *a, **o):
        beef = {"zones": {}, "states": {}, "national": None}
        src = o["nbs_file"]
        if o["nbs_url"]:
            self.stdout.write("Downloading NBS file...")
            src = download(o["nbs_url"])
        if src:
            beef = parse_nbs_beef(src)
            self.stdout.write(f"NBS: zones {list(beef['zones'])}, states {len(beef['states'])}, national {beef['national']}")
            if not beef["zones"] and not beef["states"]:
                self.stderr.write("NBS: no beef prices found in that file.")

        for c in Corridor.objects.all():
            tags, notes = [], []

            price, level = beef_price_for_state(beef, c.state)
            if price and 1500 <= price <= 30000:
                notes.append(f"beef {c.local_beef_price_ngn:,.0f} -> {price:,.0f} ({level})")
                c.local_beef_price_ngn = price
                tags.append(f"NBS beef ({level})")

            coords = CORRIDOR_COORDS.get(c.lga.lower())
            if coords and not o["skip_osm"]:
                try:
                    total, per_km2 = osm_outlets(*coords, radius_m=o["radius"])
                    if total >= 5:  # tiny counts mean the area is simply unmapped
                        notes.append(f"outlets {c.estimated_outlets} -> {int(total * OSM_FACTOR)}")
                        c.estimated_outlets = max(1, int(total * OSM_FACTOR))
                        c.outlet_density_per_km2 = round(per_km2 * OSM_FACTOR, 1)
                        tags.append("OSM outlets")
                    else:
                        notes.append(f"OSM only found {total}, kept old value")
                    time.sleep(2)  # be polite to the free Overpass servers
                except Exception as exc:
                    notes.append(f"OSM failed ({exc}), kept old value")

            if tags:
                c.data_source_tag = ("Live: " + " + ".join(tags))[:100]
                c.data_confidence = "High" if len(tags) == 2 else "Medium"
                c.last_synced = timezone.now()
                if not o["dry_run"]:
                    c.save()
            self.stdout.write(f"{c.name}: " + ("; ".join(notes) or "nothing live found"))

        self.stdout.write(self.style.SUCCESS("Dry run only, nothing saved." if o["dry_run"] else "Sync done."))