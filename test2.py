from pyxirr import xirr
from datetime import date

# Cash flows and their dates
dates = [date(2025, 7, 11), date(2025, 7, 11), date(2025, 8, 11),  date(2025, 7, 21),   date(2025, 9, 2), date(2025, 9, 2) ]
amounts = [-300000, -300000, -300000, -3000000, 1000, 3900000 ]

# Calculate XIRR
result = xirr(dates, amounts)

# Print as percentage with 2 decimal places
print(f"XIRR: {result:.2%}")
