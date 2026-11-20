# Merchant services basics

30 cards on how card acquiring works: parties, authorization, settlement, funding, fees, chargebacks and reports. Unofficial study aid built from public sources.

1. **What does an acquirer (merchant processor) do for a merchant?**
   - Authorizes card payments, settles them through the networks, funds the merchant, and carries the chargeback liability.
   - _tags: parties; source: merchant-services-guide: parties_
2. **Who is the issuer in a card payment?**
   - The cardholder's bank. It approves or declines the auth and starts disputes.
   - _tags: parties; source: merchant-services-guide: parties_
3. **What do card networks (Visa, Mastercard, Discover) do?**
   - Route and clear transactions between acquirers and issuers, set interchange and write the rules.
   - _tags: parties; source: merchant-services-guide: parties_
4. Money for a sale flows _____ -> network -> _____ -> merchant; fees flow the other way.
   - Money for a sale flows **issuer** -> network -> **acquirer** -> merchant; fees flow the other way.
   - _tags: parties, money-flow; source: merchant-services-guide: money flows_
5. **Does money move during authorization?**
   - No. The issuer only places a hold on the cardholder's available credit.
   - _tags: authorization; source: merchant-services-guide: authorization_
6. **How does the acquirer's switch pick a card network for an auth?**
   - By the card's BIN range and method of payment.
   - _tags: authorization; source: merchant-services-guide: authorization_
7. **Which merchants rely on incremental authorizations?**
   - Hotels and car rentals, where the final amount grows after the first auth.
   - _tags: authorization; source: merchant-services-guide: authorization variants_
8. **What is a $0 verification?**
   - An authorization for zero dollars that checks the card is valid without holding funds.
   - _tags: authorization; source: merchant-services-guide: authorization variants_
9. **Why reverse an authorization you won't capture?**
   - It releases the cardholder's hold and avoids network fees for unused auths, such as Mastercard's processing integrity fee.
   - _tags: authorization, fees; source: merchant-services-guide: fees_
10. Mastercard charges a processing integrity fee if an unused auth isn't reversed within _____ for card-present or _____ for card-not-present.
   - Mastercard charges a processing integrity fee if an unused auth isn't reversed within **24 hours** for card-present or **72 hours** for card-not-present.
   - _tags: authorization, fees; source: merchant-services-guide: fees_
11. **What is capture?**
   - The merchant confirming it will collect a previously authorized amount, usually when the order ships.
   - _tags: settlement; source: merchant-services-guide: settlement_
12. **What happens at batch close?**
   - The day's captured transactions are submitted to the acquirer for settlement.
   - _tags: settlement; source: merchant-services-guide: settlement_
13. **What is interchange qualification?**
   - Matching each deposit to its auth and data to decide which interchange rate applies.
   - _tags: settlement, fees; source: merchant-services-guide: settlement_
14. **What causes an interchange downgrade?**
   - Missing or stale data, like a late capture or missing address, which earns a higher rate.
   - _tags: settlement, fees; source: merchant-services-guide: settlement_
15. **What is a reject in settlement?**
   - A transaction that fails the acquirer's edits and must be fixed and resubmitted.
   - _tags: settlement; source: merchant-services-guide: settlement_
16. Funded amount = sales - _____ - _____ +/- adjustments - fees (if netted) +/- _____ moves.
   - Funded amount = sales - **refunds** - **chargebacks** +/- adjustments - fees (if netted) +/- **reserve** moves.
   - _tags: funding; source: merchant-services-guide: funding_
17. **What funding schedules can a merchant have?**
   - Daily, weekly, monthly or manual release.
   - _tags: funding; source: merchant-services-guide: funding_
18. **Which payment rails are used to fund merchants?**
   - ACH, same-day ACH, wire, or a book transfer when the account is at the same bank.
   - _tags: funding; source: merchant-services-guide: funding_
19. **What does it mean that Amex is a conveyed brand?**
   - The acquirer passes the transaction along and Amex funds the merchant directly.
   - _tags: funding, parties; source: merchant-services-guide: funding_
20. **Who receives interchange?**
   - The issuer.
   - _tags: fees; source: merchant-services-guide: fees_
21. **Who receives assessments?**
   - The card brand (network), as a percentage of volume.
   - _tags: fees; source: merchant-services-guide: fees_
22. **Name the common merchant pricing plans.**
   - Interchange-plus, tiered, flat rate, and swiped/keyed.
   - _tags: fees, pricing; source: merchant-services-guide: pricing_
23. **How does interchange-plus pricing work?**
   - The merchant pays actual interchange and assessments, plus a fixed acquirer markup.
   - _tags: fees, pricing; source: merchant-services-guide: pricing_
24. **When do card brands usually update interchange rates?**
   - Twice a year, in April and October.
   - _tags: fees; source: merchant-services-guide: fees_
25. **How is the effective merchant discount rate (EMDR) calculated?**
   - Total processing cost divided by sales volume.
   - _tags: fees; source: merchant-services-guide: fees_
26. **What is a retrieval request?**
   - The issuer asking for transaction proof before a dispute. No money moves.
   - _tags: chargebacks; source: merchant-services-guide: chargebacks_
27. **What happens to the merchant's money on a first chargeback?**
   - The disputed amount is debited from the merchant.
   - _tags: chargebacks; source: merchant-services-guide: chargebacks_
28. **What is representment?**
   - The merchant fighting a chargeback by sending evidence back through the acquirer.
   - _tags: chargebacks; source: merchant-services-guide: chargebacks_
29. Dispute stages: retrieval -> first chargeback -> _____ -> _____ -> arbitration.
   - Dispute stages: retrieval -> first chargeback -> **representment** -> **pre-arbitration** -> arbitration. (Arbitration is decided by the card network.)
   - _tags: chargebacks; source: merchant-services-guide: chargebacks_
30. **On a merchant's reports, which key joins one sale across auth, deposit, funding and chargeback records?**
   - The transaction reference. For online orders, the order number and gateway reference.
   - _tags: reporting; source: merchant-services-guide: data model_
