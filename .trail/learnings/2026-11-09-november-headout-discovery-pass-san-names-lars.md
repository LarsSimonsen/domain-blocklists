---
title: "November Headout discovery pass: SAN names now redirect, affiliates dominate keyword hits, retry on www"
author: Lars
date: 2026-11-09
branch: claude/headout-discovery-2026-11
cost: { minutes: 1, tokens: 1366 }
id: l-33a259be
scope: repo
status: active
src: agent
touches:
  - README.md
  - data/headout.yaml
  - lists/headout/adguard.txt
  - lists/headout/domains.txt
  - lists/headout/pihole.txt
---

## Decided
- 2026-11-09 exhaustive pass (~126k generated names over sitemap, variant, localization, SAN, CT, search and outbound-link lanes) yielded 5 operated records. Saturation reached for the generated lanes; about 2k names stayed unavailable after apex and www retries.
- Most names in live Headout certificate SANs that are not yet listed now 30x-redirect to a sub-path of another Headout hostname (e.g. belemtowertickets.com -> tickets-lisbon.com/belem-tower/). By the rules a redirect verifies nothing, so they stay rejected.
- When the apex fails TLS or times out, retry `candidate` on `www.<name>`; Headout sites often serve only www. This turned up two of the five records.

## Tried and ruled out
- Treating /16 overlap with verified records as a "Headout CDN" tier: Cloudflare prefixes (104.21, 172.67) put most unrelated sites in it. Restrict to CloudFront prefixes.
- crt.sh: still 502. Cert Spotter history added no names beyond the live SANs.

## Watch out
- About 35 of 42 keyword hits were Web Maremma affiliate sites (an "Affiliate Disclosure ... operated by Web Maremma" line) plus Cruise Media and comparison sites that list Headout as a partner. Auto-reject on those operator strings before reading.
- headout.es is a parked for-sale page that names Headout. A name match is not evidence.
- elbphilharmonietours.com uses an older template (Company Name / "run by Headout", Cloudflare hosting, empty address). Flagged for the maintainer.

In the code: DNS prefilter speedup — an NXDOMAIN on A already covers AAAA, so skip the AAAA query; 96 keep-alive threads ran about 5k names/min against Cloudflare and Google DoH.
