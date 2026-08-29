"""
Management command to seed the database with 25 realistic tech-accessory products.

Products span 4 categories: keyboards, headphones, monitors, mice.
Some are genuinely suitable for programming; some are genuinely not.
"""

import random

from django.core.management.base import BaseCommand
from faker import Faker

from catalogue.models import Product

fake = Faker()

# ---------------------------------------------------------------------------
# Product templates — each dict is expanded into one Product row.
# `programming_fit` is metadata only (not stored); it guided the description.
# ---------------------------------------------------------------------------
PRODUCT_TEMPLATES = [
    # ── KEYBOARDS ──────────────────────────────────────────────────────────
    {
        "name": "ProType MX Mechanical Keyboard",
        "category": "keyboards",
        "price_range": (899900, 1299900),   # ₹8,999 – ₹12,999
        "rating_range": (4.3, 4.9),
        "description": (
            "Full-size mechanical keyboard with Cherry MX Brown switches, "
            "individually programmable RGB back-lighting, dedicated macro keys, "
            "and a detachable magnetic wrist rest. N-key rollover and USB-C "
            "connectivity make it ideal for long programming sessions. "
            "Split space-bar option available for ergonomic thumb use."
        ),
        "programming_fit": True,
    },
    {
        "name": "CodeBoard 75% Hot-Swap Keyboard",
        "category": "keyboards",
        "price_range": (699900, 899900),
        "rating_range": (4.5, 4.8),
        "description": (
            "Compact 75% layout with hot-swappable Gateron switches, "
            "PBT double-shot keycaps, and QMK/VIA firmware support for "
            "fully custom key mapping. Built-in USB hub and sound-dampening "
            "foam. Designed for developers who value desk space without "
            "sacrificing the function row."
        ),
        "programming_fit": True,
    },
    {
        "name": "GlowStrike Mini Gaming Keyboard",
        "category": "keyboards",
        "price_range": (249900, 399900),
        "rating_range": (3.5, 4.2),
        "description": (
            "60% membrane gaming keyboard with per-key RGB and "
            "anti-ghosting on WASD cluster. Lightweight plastic body, "
            "no function row, no dedicated arrow keys. Optimised for "
            "fast-paced FPS gaming rather than extended typing."
        ),
        "programming_fit": False,
    },
    {
        "name": "TravelType Foldable Bluetooth Keyboard",
        "category": "keyboards",
        "price_range": (179900, 299900),
        "rating_range": (3.0, 3.8),
        "description": (
            "Ultra-portable tri-fold Bluetooth keyboard weighing just 180 g. "
            "Scissor-switch keys with 1.5 mm travel. Pairs with up to 3 "
            "devices. Great for quick emails on a tablet but the cramped "
            "layout and shallow travel make it unsuitable for hours of coding."
        ),
        "programming_fit": False,
    },
    {
        "name": "ErgoSplit V2 Ortholinear Keyboard",
        "category": "keyboards",
        "price_range": (1299900, 1799900),
        "rating_range": (4.6, 5.0),
        "description": (
            "Split ergonomic ortholinear keyboard with columnar stagger, "
            "tenting legs, and programmable thumb clusters. Runs ZMK "
            "firmware with Bluetooth 5.2. Each half connects wirelessly. "
            "Drastically reduces wrist strain during 10+ hour coding days. "
            "Includes sculpted DSA keycaps optimised for touch-typing."
        ),
        "programming_fit": True,
    },
    {
        "name": "BudgetClack Starter Keyboard",
        "category": "keyboards",
        "price_range": (89900, 149900),
        "rating_range": (2.8, 3.5),
        "description": (
            "Entry-level full-size membrane keyboard with spill-resistant "
            "design. Mushy key feel with limited tactile feedback. Works "
            "fine for casual browsing but the inconsistent key registration "
            "makes fast typing frustrating for software development."
        ),
        "programming_fit": False,
    },
    {
        "name": "SilentType Wireless Low-Profile Keyboard",
        "category": "keyboards",
        "price_range": (549900, 749900),
        "rating_range": (4.2, 4.7),
        "description": (
            "Low-profile wireless mechanical keyboard with Kailh Choc "
            "switches rated for ultra-quiet operation (<25 dB). Full-size "
            "layout with dedicated media keys and a built-in trackpad. "
            "2.4 GHz and Bluetooth 5.0 dual connectivity, 40-hour battery. "
            "The quiet keys and comfortable typing angle suit shared-office "
            "programming environments."
        ),
        "programming_fit": True,
    },

    # ── HEADPHONES ─────────────────────────────────────────────────────────
    {
        "name": "FocusPods ANC Over-Ear Headphones",
        "category": "headphones",
        "price_range": (799900, 1199900),
        "rating_range": (4.4, 4.9),
        "description": (
            "Over-ear headphones with hybrid active noise cancellation "
            "(-35 dB), transparency mode, and a balanced sound profile "
            "with clear mids for voice and video calls. 30-hour battery, "
            "multi-point Bluetooth. Perfect for developers working in "
            "open-plan offices or co-working spaces."
        ),
        "programming_fit": True,
    },
    {
        "name": "BassBlaster 5000 Gaming Headset",
        "category": "headphones",
        "price_range": (349900, 499900),
        "rating_range": (3.6, 4.3),
        "description": (
            "Closed-back gaming headset with 50 mm drivers tuned for "
            "heavy sub-bass, virtual 7.1 surround, and RGB ear cups. "
            "Boom microphone with noise gate. Emphasises explosions and "
            "gunshots over vocal clarity — not ideal for long conference "
            "calls or podcast-heavy workflows."
        ),
        "programming_fit": False,
    },
    {
        "name": "ClearCall Pro Wireless Headset",
        "category": "headphones",
        "price_range": (599900, 849900),
        "rating_range": (4.2, 4.7),
        "description": (
            "Lightweight on-ear wireless headset designed for all-day "
            "wear during stand-ups and pair-programming sessions. "
            "CVC 8.0 noise-cancelling dual microphone, 24-hour battery, "
            "and a flat, neutral sound signature. Certified for MS Teams "
            "and Zoom. Flip-to-mute boom arm."
        ),
        "programming_fit": True,
    },
    {
        "name": "ThumperX Wireless Earbuds",
        "category": "headphones",
        "price_range": (149900, 249900),
        "rating_range": (3.2, 3.9),
        "description": (
            "True-wireless earbuds with 12 mm dynamic drivers and a "
            "V-shaped EQ emphasising bass and treble. IPX5 water "
            "resistance for gym use. Short 4-hour battery per charge. "
            "No ANC, no multi-point — mainly for music during workouts."
        ),
        "programming_fit": False,
    },
    {
        "name": "StudioMonitor SM-7 Headphones",
        "category": "headphones",
        "price_range": (999900, 1499900),
        "rating_range": (4.5, 4.9),
        "description": (
            "Open-back reference headphones with planar-magnetic drivers "
            "delivering an exceptionally flat frequency response. "
            "Replaceable velour ear pads and lightweight magnesium frame "
            "for marathon listening. Excellent for developers who also "
            "produce music or need fatigue-free audio during deep work."
        ),
        "programming_fit": True,
    },
    {
        "name": "NeonBeats Party Headphones",
        "category": "headphones",
        "price_range": (99900, 179900),
        "rating_range": (2.5, 3.4),
        "description": (
            "Flashy over-ear headphones with LED-lit ear cups that pulse "
            "to the beat. Heavy at 380 g with a plasticky build. Boosted "
            "bass bleeds into mids, making podcasts and calls muddy. "
            "A novelty party accessory, not a productivity tool."
        ),
        "programming_fit": False,
    },

    # ── MONITORS ───────────────────────────────────────────────────────────
    {
        "name": "UltraView 34\" UWQHD Curved Monitor",
        "category": "monitors",
        "price_range": (3499900, 4999900),
        "rating_range": (4.5, 4.9),
        "description": (
            "34-inch ultra-wide curved IPS monitor (3440×1440) with 98% "
            "sRGB coverage, USB-C 90 W power delivery, and KVM switch. "
            "Picture-by-picture lets you view two full sources side by "
            "side. An excellent monitor for programming — fits a code "
            "editor, terminal, and browser without alt-tabbing."
        ),
        "programming_fit": True,
    },
    {
        "name": "DevPanel 27\" 4K IPS Monitor",
        "category": "monitors",
        "price_range": (2499900, 3299900),
        "rating_range": (4.4, 4.8),
        "description": (
            "27-inch 4K (3840×2160) IPS panel with factory-calibrated "
            "Delta E < 2, anti-glare coating, and an ergonomic stand "
            "with height, tilt, swivel, and pivot adjustments. VESA "
            "mount compatible. Text is razor-sharp — perfect for reading "
            "dense code and documentation for hours."
        ),
        "programming_fit": True,
    },
    {
        "name": "SpeedFrame 24\" 360 Hz Gaming Monitor",
        "category": "monitors",
        "price_range": (2999900, 3999900),
        "rating_range": (4.0, 4.5),
        "description": (
            "24.5-inch Full HD (1920×1080) TN panel with 360 Hz refresh "
            "rate, 0.5 ms response time, and G-Sync support. Colour "
            "accuracy is poor (62% sRGB) and the low resolution means "
            "text rendering is fuzzy. Built purely for competitive esports, "
            "not for reading or writing code."
        ),
        "programming_fit": False,
    },
    {
        "name": "EcoBright 21\" HD Monitor",
        "category": "monitors",
        "price_range": (699900, 999900),
        "rating_range": (2.5, 3.3),
        "description": (
            "21.5-inch HD (1920×1080) VA panel with 60 Hz refresh rate "
            "and fixed tilt-only stand. Mediocre 250-nit brightness and "
            "limited viewing angles. Adequate for basic office tasks but "
            "the small screen real estate is limiting for any serious "
            "multi-file development workflow."
        ),
        "programming_fit": False,
    },
    {
        "name": "DualStack 28\" 4K HDR Monitor",
        "category": "monitors",
        "price_range": (3999900, 5499900),
        "rating_range": (4.3, 4.8),
        "description": (
            "28-inch 4K IPS monitor with HDR 600 certification, 95% "
            "DCI-P3 colour gamut, and built-in KVM for switching between "
            "a work laptop and personal machine. USB-C hub with ethernet "
            "pass-through. Equally suited for programming, design work, "
            "and media consumption."
        ),
        "programming_fit": True,
    },
    {
        "name": "PortaView 15.6\" Portable Monitor",
        "category": "monitors",
        "price_range": (1299900, 1799900),
        "rating_range": (3.8, 4.4),
        "description": (
            "15.6-inch Full HD IPS portable monitor with USB-C and mini "
            "HDMI input. Weighs 750 g with a built-in kickstand cover. "
            "Handy as a secondary display while travelling, but the small "
            "size and 1080p resolution make it a compromise for daily "
            "programming use compared to a full desktop panel."
        ),
        "programming_fit": False,
    },

    # ── MICE ───────────────────────────────────────────────────────────────
    {
        "name": "PrecisionGlide Ergonomic Mouse",
        "category": "mice",
        "price_range": (399900, 599900),
        "rating_range": (4.4, 4.9),
        "description": (
            "Vertical ergonomic wireless mouse with a 57-degree grip "
            "angle, adjustable DPI (800–4000), silent clicks, and a "
            "sculpted thumb rest. Dual-mode Bluetooth/2.4 GHz dongle. "
            "Reduces forearm pronation during marathon debugging sessions. "
            "Ideal for programmers with RSI concerns."
        ),
        "programming_fit": True,
    },
    {
        "name": "SwiftClick Ultra-Light Gaming Mouse",
        "category": "mice",
        "price_range": (499900, 749900),
        "rating_range": (4.0, 4.5),
        "description": (
            "Ultra-light (58 g) honeycomb-shell gaming mouse with a "
            "26000 DPI optical sensor, 1000 Hz polling rate, and "
            "paracord cable. Ambidextrous shape with no thumb rest. "
            "Built for competitive FPS flick-shots — fast but not "
            "comfortable for 8 hours of coding and scrolling."
        ),
        "programming_fit": False,
    },
    {
        "name": "ThinkPad TrackPoint Wireless Mouse",
        "category": "mice",
        "price_range": (249900, 349900),
        "rating_range": (4.1, 4.6),
        "description": (
            "Compact wireless mouse with a TrackPoint nub in the centre "
            "for precise cursor micro-adjustments without lifting fingers. "
            "Quiet tactile scroll wheel. USB-C rechargeable with 3-month "
            "battery life. A no-nonsense productivity mouse loved by "
            "developers and sysadmins."
        ),
        "programming_fit": True,
    },
    {
        "name": "MegaClaw RGB Gaming Mouse",
        "category": "mice",
        "price_range": (199900, 349900),
        "rating_range": (3.0, 3.8),
        "description": (
            "Heavy (120 g) claw-grip gaming mouse with 12 programmable "
            "side buttons and 16.8 million colour RGB lighting zones. "
            "Designed for MMO gamers who need macro keys. The bulk and "
            "aggressive shape cause hand fatigue during everyday "
            "office or coding work."
        ),
        "programming_fit": False,
    },
    {
        "name": "ScrollMaster Pro Wireless Mouse",
        "category": "mice",
        "price_range": (599900, 899900),
        "rating_range": (4.5, 4.9),
        "description": (
            "Full-size wireless mouse with a MagSpeed electromagnetic "
            "scroll wheel that auto-shifts between ratchet and free-spin "
            "modes. Ergonomic sculpted shape, Darkfield sensor works on "
            "glass, and USB-C quick charge (1 min = 3 hours). Perfect "
            "for scrolling through large codebases and documentation."
        ),
        "programming_fit": True,
    },
    {
        "name": "BasicClick USB Wired Mouse",
        "category": "mice",
        "price_range": (29900, 69900),
        "rating_range": (2.2, 3.0),
        "description": (
            "No-frills 3-button USB wired mouse with a basic optical "
            "sensor (1000 DPI fixed). Symmetrical shape, rubber scroll "
            "wheel, 1.5 m cable. Functional but the lack of adjustable "
            "DPI, side buttons, and ergonomic shaping make prolonged use "
            "uncomfortable for desk-bound developers."
        ),
        "programming_fit": False,
    },
]


class Command(BaseCommand):
    help = "Seed the database with 25 realistic tech-accessory products."

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete all existing products before seeding.",
        )

    def handle(self, *args, **options):
        if options["clear"]:
            deleted, _ = Product.objects.all().delete()
            self.stdout.write(self.style.WARNING(f"Deleted {deleted} existing product(s)."))

        products = []
        for tmpl in PRODUCT_TEMPLATES:
            price = random.randint(*tmpl["price_range"])
            rating = round(random.uniform(*tmpl["rating_range"]), 1)
            stock = random.randint(0, 150)

            products.append(
                Product(
                    name=tmpl["name"],
                    category=tmpl["category"],
                    price_paise=price,
                    rating=rating,
                    stock=stock,
                    description=tmpl["description"],
                )
            )

        Product.objects.bulk_create(products)
        self.stdout.write(
            self.style.SUCCESS(f"Successfully seeded {len(products)} products.")
        )

        # Summary
        from collections import Counter
        cats = Counter(p.category for p in products)
        for cat, count in sorted(cats.items()):
            self.stdout.write(f"  {cat}: {count}")
