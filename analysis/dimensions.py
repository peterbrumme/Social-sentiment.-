"""Homebuilder sentiment dimensions and shared label schema."""

DIMENSIONS = {
    "build_quality": "Build quality and craftsmanship",
    "sales_contract": "Sales and contract experience",
    "timeline_delays": "Construction timeline and delays",
    "service_warranty": "Customer service and warranty response",
    "price_value": "Price and value perception",
    "community": "Community and neighborhood satisfaction",
}

# Keyword hints used by the local fallback to decide which dimensions an item speaks to.
KEYWORDS = {
    "build_quality": ["quality", "craftsmanship", "defect", "crack", "drywall", "foundation", "leak", "roof", "siding",
                      "flooring", "framing", "workmanship", "shoddy", "sloppy", "poorly built", "well built", "mold",
                      "plumbing", "hvac", "windows", "paint", "punch list", "inspection"],
    "sales_contract": ["sales", "salesperson", "agent", "contract", "closing", "upgrade", "options", "lender", "incentive",
                       "rate lock", "bait", "deposit", "design center", "realtor", "negotiat"],
    "timeline_delays": ["delay", "delayed", "timeline", "schedule", "months", "on time", "behind", "closing date",
                        "move-in", "move in", "waiting", "pushed back", "completion"],
    "service_warranty": ["warranty", "customer service", "service", "response", "repair", "callback", "ignored",
                         "responsive", "fixed", "support", "complain", "manager", "communication"],
    "price_value": ["price", "overpriced", "value", "worth", "cost", "expensive", "cheap", "money", "afford",
                    "price increase", "hidden fees", "upgrade costs"],
    "community": ["neighborhood", "community", "hoa", "neighbors", "location", "schools", "amenities", "lot",
                  "development", "traffic", "commute"],
}

SENTIMENTS = ("positive", "neutral", "negative")
