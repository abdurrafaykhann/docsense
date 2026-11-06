"""Faker provider with Pakistani business flavour (names, NTN/STRN, PKR catalogue)."""

from __future__ import annotations

from faker.providers import BaseProvider

SURNAMES = [
    "Ahmed", "Khan", "Malik", "Qureshi", "Siddiqui", "Hashmi", "Rehman", "Butt", "Chaudhry",
    "Sheikh", "Baig", "Mirza", "Ansari", "Farooqi", "Niazi", "Jamil", "Iqbal", "Hussain",
]  # fmt: skip
TRADES = {
    "grocery": ["General Store", "Mart", "Traders", "Super Store", "Kiryana House"],
    "electronics": ["Electronics", "Electric Store", "Mobile Zone", "Trading Co"],
    "pharmacy": ["Pharmacy", "Medical Store", "Chemist"],
    "hardware": ["Hardware House", "Building Materials", "Paint & Tools"],
    "restaurant": ["Restaurant", "Karahi House", "Biryani Centre", "Cafe"],
    "services": ["Consultants", "IT Solutions", "Services (Pvt) Ltd", "Associates"],
}
PREFIXES = [
    "Al-",
    "Bismillah ",
    "Noor ",
    "Madina ",
    "Karachi ",
    "Lahore ",
    "Royal ",
    "New ",
    "Pak ",
]
URDU_NAMES = [
    "السلام جنرل اسٹور", "المدینہ ٹریڈرز", "بسم اللہ مارٹ", "نور فارمیسی",
    "رحمان اینڈ سنز", "کراچی الیکٹرانکس", "پاک سروسز", "ملک بروادرز",
]  # fmt: skip
CITIES = {
    "Karachi": ["Saddar", "Gulshan-e-Iqbal", "Clifton", "North Nazimabad", "DHA Phase 5"],
    "Lahore": ["Gulberg III", "Model Town", "Anarkali", "Johar Town", "Liberty Market"],
    "Islamabad": ["F-7 Markaz", "Blue Area", "G-9", "I-8 Markaz"],
    "Rawalpindi": ["Saddar", "Raja Bazaar", "Bahria Town"],
    "Faisalabad": ["D Ground", "Peoples Colony"],
    "Peshawar": ["University Town", "Saddar Road"],
    "Multan": ["Cantt", "Nusrat Road"],
}
# (description, unit, low, high) in PKR
CATALOG = {
    "grocery": [
        ("Basmati Rice 5kg", "pc", 1450, 2100),
        ("Cooking Oil 1L", "pc", 520, 640),
        ("Sugar 1kg", "kg", 140, 180),
        ("Tea Packet 190g", "pc", 190, 380),
        ("Fresh Milk 1L", "pc", 210, 270),
        ("Eggs (dozen)", "dz", 280, 360),
        ("Flour 10kg", "pc", 1100, 1500),
        ("Biscuits Family Pack", "pc", 60, 160),
        ("Red Chilli Powder 200g", "pc", 180, 320),
        ("Dal Chana 1kg", "kg", 240, 330),
    ],
    "electronics": [
        ("LED Bulb 12W", "pc", 350, 650),
        ("Extension Cord 5m", "pc", 900, 1800),
        ("Phone Charger 20W", "pc", 1200, 2600),
        ("USB Cable Type-C", "pc", 250, 700),
        ("Power Bank 10000mAh", "pc", 3500, 6500),
        ("Table Fan 16in", "pc", 7500, 11500),
        ("Wall Socket Switch", "pc", 120, 380),
        ("Earphones", "pc", 450, 1600),
    ],
    "pharmacy": [
        ("Paracetamol 500mg strip", "pc", 25, 60),
        ("Cough Syrup 120ml", "pc", 150, 330),
        ("Vitamin C 500mg", "pc", 250, 520),
        ("Antiseptic Cream", "pc", 90, 220),
        ("Face Mask (box)", "pc", 180, 420),
        ("Digital Thermometer", "pc", 450, 950),
    ],
    "hardware": [
        ("Cement Bag 50kg", "pc", 1050, 1350),
        ("Emulsion Paint 4L", "pc", 2800, 5200),
        ("PVC Pipe 1in", "pc", 380, 720),
        ("Steel Nails 1kg", "kg", 260, 410),
        ("Hand Drill", "pc", 4200, 9800),
        ("Paint Brush Set", "pc", 350, 900),
    ],
    "restaurant": [
        ("Chicken Karahi (Full)", "pc", 1800, 2800),
        ("Mutton Biryani", "pc", 650, 1100),
        ("Naan", "pc", 25, 45),
        ("Soft Drink 1.5L", "pc", 190, 260),
        ("Seekh Kabab (4 pc)", "pc", 600, 900),
        ("Raita", "pc", 60, 120),
        ("Gulab Jamun", "pc", 150, 260),
    ],
    "services": [
        ("IT Support (hours)", "hr", 2500, 6000),
        ("Consultancy (hours)", "hr", 4000, 12000),
        ("Website Maintenance", "mo", 15000, 45000),
        ("Printing & Binding", "pc", 800, 4500),
        ("Delivery Charges", "pc", 250, 900),
        ("Annual Software Licence", "pc", 20000, 90000),
    ],
}


class PakistaniProvider(BaseProvider):
    def category(self) -> str:
        return self.random_element(list(CATALOG))

    def business(self, category: str) -> tuple[str, str]:
        """(english_name, urdu_name)"""
        r = self.generator.random
        trade = r.choice(TRADES[category])
        base = r.choice(SURNAMES)
        name = (
            r.choice(PREFIXES) + trade
            if r.random() < 0.4
            else f"{base} {'& Sons ' if r.random() < 0.3 else ''}{trade}".replace("  ", " ")
        ).strip()
        return name, r.choice(URDU_NAMES)

    def city_area(self) -> tuple[str, str]:
        r = self.generator.random
        city = r.choice(list(CITIES))
        return city, r.choice(CITIES[city])

    def address(self) -> str:
        r = self.generator.random
        city, area = self.city_area()
        return f"Shop {r.randint(1, 120)}, {area}, {city}"

    def phone_pk(self) -> str:
        r = self.generator.random
        return f"03{r.randint(0, 4)}{r.randint(0, 9)}-{r.randint(1000000, 9999999)}"

    def ntn(self) -> str:
        r = self.generator.random
        digits = "".join(str(r.randint(0, 9)) for _ in range(7))
        return f"{digits}-{r.randint(0, 9)}"

    def strn(self) -> str:
        r = self.generator.random
        if r.random() < 0.65:
            return "".join(str(r.randint(0, 9)) for _ in range(13))
        d = "".join(str(r.randint(0, 9)) for _ in range(17))
        return f"{d[:2]}-{d[2:4]}-{d[4:8]}-{d[8:11]}-{d[11:]}"

    def catalog(self, category: str):
        return CATALOG[category]
