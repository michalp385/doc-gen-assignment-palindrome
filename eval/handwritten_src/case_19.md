# Case 19: two report instructions that disagree

**Rule:** §8.4, D16
**Expected release:** failed generation

## Account data

```json
{
  "snapshot_date": "2026-05-01",
  "holders": {
    "client": {
      "name": "Warren Betts",
      "accounts": [
        {
          "account_id": "WB-ISA-01",
          "platform": "Holloway",
          "type": "Stocks & Shares ISA",
          "owner": "Warren Betts",
          "status": "open",
          "value": 37000.0,
          "currency": "GBP",
          "valuation_date": "2026-05-01"
        },
        {
          "account_id": "WB-CASH-01",
          "platform": "Holloway",
          "type": "Cash Account",
          "owner": "Warren Betts",
          "status": "open",
          "value": 12000.0,
          "currency": "GBP",
          "valuation_date": "2026-05-01"
        },
        {
          "account_id": "WB-GIA-01",
          "platform": "Holloway",
          "type": "General Investment Account",
          "owner": "Warren Betts",
          "status": "open",
          "value": 19000.0,
          "currency": "GBP",
          "valuation_date": "2026-05-01"
        }
      ]
    }
  }
}
```

## Meeting notes

Annual review meeting with Warren Betts, held 21 May 2026.

Warren confirmed his circumstances and objectives are unchanged and remains comfortable with a moderate approach to risk.

Warren would like to move £5,000 from his Holloway cash account into his Stocks & Shares ISA.

We agreed he would move £5,000 from the cash account into the Stocks & Shares ISA. No investments are being sold.

Warren has no income requirement from the portfolio.

Next steps: prepare the advice report covering the ISA top-up.


## Report instruction

Filename: report_request.docx

Adviser | Daniel Reeves
Accounts covered | Holloway Stocks & Shares ISA
Investment amount | GBP 5,000
Source of funds | Cash held on deposit in the Holloway cash account
Selling existing investments? | No
Product recommended | Top up of existing Stocks & Shares ISA
Held in single or joint name? | Single
Agreed risk profile | 4 (moderate)
Initial charge | 0%

## Report instruction

Filename: report_request_2.docx

Adviser | Daniel Reeves
Accounts covered | Holloway Stocks & Shares ISA and General Investment Account
Investment amount | GBP 9,000
Source of funds | General Investment Account
Selling existing investments? | Yes
Product recommended | Top up of existing Stocks & Shares ISA
Held in single or joint name? | Single
Agreed risk profile | 4 (moderate)
Initial charge | 0%
