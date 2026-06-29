# Equity Volatility Strategy

Thinking Outside the Box for Tail Trading

In tail risk hedging, the focus often lies on put payoffs and ways to minimize drag. However, we find that the principle of “you pay for what you get” frequently applies – i.e. cheap hedges may under protect, while those that fully protect may bleed too much.

• What about a strategy that delivers robust PnL in a tail-like period, without paying any insurance cost while waiting for the event? We conducted a deep-dive to find unique market behaviors during these periods.   
• Tail events present three distinct trading opportunities in the Delta, Gamma, and Vega spaces, with the report detailing optimal implementations for each.   
• These opportunities are structured into a three-pillar framework that diversifies risk and enhances PnL delivery with low drawdown.   
• The new three-leg Tail-Trading Strategy serves as a powerful diversifier to traditional systematic hedging methods and CTA trend strategies, significantly enhancing performance.   
• By combining the Tail-Trading Strategy with traditional systematic Put-Spread hedging, we demonstrate the most robust protection for long SPX portfolios, improving returns, Sharpe ratio, worst 1D and max DD. This approach offers a comprehensive solution to tail -isk management, effectively balancing protection and profitability in volatile market conditions.

![](images/d135559490b7f88ac05fd3ebcee1140ea2f634035e7b05f9296e16b6369c4aae.jpg)  
Figure 1: PnL of the New Tail Trading Strategy Contribution from the Three Pillars   
Source: OPRA, J.P. Morgan Equity Derivatives Strategy

Please vote 5 Stars for JPM in each sector (firm vote) and 5 Stars for each analyst (individual vote). You can request a ballot at extelinsights.com/voting. Thank you for your consideration.

# Global Quantitative and Derivatives Strategy

Yangyang Hou AC (44-20) 3493-1012 yangyang.hou@jpmorgan.com J.P. Morgan Securities plc

Emma Wu AC (1-212) 834-2174 emma.wu@jpmorgan.com J.P. Morgan Securities LLC

Dobromir Tzotchev, PhD AC (44-20) 7134-5331 dobromir.tzotchev@jpmorgan.com J.P. Morgan Securities plc

Tony SK Lee   
(852) 2800-8857   
tony.sk.lee@jpmorgan.com   
J.P. Morgan Securities (Asia Pacific) Limited/ J.P. Morgan Broking (Hong Kong) Limited Twinkle Mehta, CFA   
(852) 2800-7109   
twinkle.mehta@jpmorgan.com   
J.P. Morgan Securities (Asia Pacific) Limited/ J.P. Morgan Broking (Hong Kong) Limited

Davide Silvestrini (44-20) 7134-4082 davide.silvestrini@jpmorgan.com J.P. Morgan Securities plc

Thomas Salopek (1-212) 834-5476 thomas.salopek@jpmorgan.com J.P. Morgan Securities LLC

Bram Kaplan, CFA (1-212) 272-1215 bram.kaplan@jpmorgan.com J.P. Morgan Securities LLC

We would appreciate your support for J.P. Morgan in the 2025 US Extel Survey in the following macro categories: •Equity-Linked Strategies (Tony Lee) •Portfolio Strategy (Dubravko Lakos) •Quantitative Research (Dubravko Lakos) •Thematic Research (Bhupinder Singh) •Technical Analysis (Jason Hunter)

# See page 23 for analyst certification and important disclosures.

J.P. Morgan does and seeks to do business with companies covered in its research reports. As a result, investors should be aware that the firm may have a conflict of interest that could affect the objectivity of this report. Investors should consider this report as only a single factor in making their investment decision.

# Table Of Contents

# Think Outside the Box for Tail-Hedging. 3

Identifying the Tail-Like Period with Term Structure Inversion . . . 4   
Tail-like Market Behavior for Spot, Skew, Real and Implied Vol . . 5

3 Avenues for Trading Opportunities . 9

Profiting from Spot Return in Delta Space. . . 9   
Profiting from Realized Vol and Upside Skew in Gamma Space . . . 11   
Profiting from Normalization in the VIX in Vega Space. . . 13

3 Pillar Framework for PnL Delivery . 15

# Useful Applications in Practice. . . 17

Overlay to Systematic Hedging Strategies in Equity . . . . 17   
Overlay to SPX CTA Style Trend Following . . 19   
Other Considerations . 20   
Reality Check on Tail-Period Liquidity. 21   
Appendix. . 22

# Think Outside the Box for Tail-Hedging

With the explosion of SPX buy-write option embedded ETFs, we conducted a deep dive to see how to improve the performance. A by-product of the study identified optimal times to actually BUY call options instead of selling them. In summary:

1. When the trend momentum is too strong, Buy OTM call outright (unhedged)   
2. When the market is in distress, Buy OTM call, both outright and delta-hedged

The second condition is less obvious, as investors normally think that, in distressed markets, volatility is higher, allowing for profit from selling calls at a higher premium. However, those are days when short calls experience the biggest drawdown. And this is the key to the note today – the options market tends to underprice the probability of a gapping up in a distressed market.

We came across an interesting piece of feedback when we showed the chart below from point 2: “This chart looks like a tail-hedge strategy, but why doesn’t it bleed?”

\$10mio Notional Per Trade when “market in distress” signal triggered \*No bid-offer cost included Source: Bloomberg Finance L.P., J.P. Morgan Equity Derivatives Strategy

![](images/7fa75d245503a9047e1d5129218aa46ef3dc6ec807cf9f0b41b963c0656dc702.jpg)  
Figure 2: SPX Long 1M 25D Call Acc Pnl

This prompted further studies to think outside the box – typically, tail-hedge studies focus on minimizing the cost of drag. However, we often encounter the “you pay for what you get” effect, where cheaper options can be under-protected, while more pricey ones result in excessive bleeding. Regardless, there is always an insurance cost involved.

But what does tail hedging truly mean? Is it merely about achieving substantial PnL during tail periods to offset losses from long-only investments? If so, what about not paying anything to try to time the tail event, but a strategy that simply delivers significant PnL during tail event periods?

# Identifying the Tail-Like Period with Term Structure Inversion

First, how do we define tail-like period? If we consider a move in SPX of minus $\mathbf { 3 x }$ standard deviation over 1D, 5D to 10D returns, there are fewer than 80 occurrences in the data since 2004. Lowering this threshold to $- 2 \mathbf { X }$ stdev increases the number of events to 200 (Figure 3When ayof1,5 02Dretuns wrelthan -2Sigma, 3M-1term sucteand VIXlevs). But we know that equity portfolios can suffer over much longer time spans than just those few days.

How about using implied vol measures, such as the VIX, to identify tail periods? Even for -2 sigma events, the VIX has ranged from 20 to 70, which is quite wide (Figure 3When ayof1,5 02Dretuns wrelthan -2Sigma, 3M-1term sucteand VIXlevs). If we use a specific VIX value as a cutoff, we must account for different vol regimes, otherwise, all dates in high vol regimes would be flagged.

A more persistent and “clean” observation during the tail-like period is that the 3M-1M implied vol term structure is consistently negative. We examined the spot returns on days when the term structure turned negative, which occurred over 1,000 times, and confirmed that these instances were always associated with high standard deviation moves in SPX returns, averaging at 1.95 sigma (Figure 4When 3M-1term suctewa ngive,SPX rtunswe alythig smacore).

Data from 2004

![](images/7960971fd2ec9996d25fba30d8357d9db89898d824bbd24ec9ddac70c1c8be5b.jpg)  
Figure 3: When any of 1, 5, 10, 22D returns were less than -2 Sigma, 3M-1M term structure and VIX levels

Data from 2004

![](images/0c0cb37ba61e1d57a6b89df07a0a4588db67934f8cd7f26da4157d522dd2eed7.jpg)  
Figure 4: When 3M-1M term structure was negative, SPX returns were always at a high sigma score   
Sigma score is the max(standard deviation of 1,5,10,22D absolute return) Source: Bloomberg Finance L.P., J.P. Morgan Equity Derivatives Strategy

When determining which tenor of the term structure to use as a signal, we find that the 1M-1W tenor is too noisy, while 3M-1Y tenor can be slightly slow. The inversion of the 3M-1M term structure appears to be the most robust, and for good reason: the 3M tenor is crucial for option market making, as its vega is half that of the 1Y tenor while still possessing significant gamma. The 1M tenor serves as another key anchor point, making these two maturities theoretically the most efficiently priced. Therefore, an inversion of these two points is very meaningful and robust in capturing market “tail-like moments”, without needing to account for different volatility regimes.

# Tail-like Market Behavior for Spot, Skew, Real and Implied Vol

By dividing the market into “normal days” and “tail-like days” based on whether the term structure is negative, we have some interesting findings in both the spot and vol spaces. To ensure no missing results, we included days where either the 3M/1M ATMF vol is inverted or UX3/UX1 is inverted, categorizing these as $\mathrm { T S } { < } 0$ days.

# Spot Return

When comparing SPX spot returns following days when the TS turned negative (Figure 5Subseqnt SpoReurn Distbuon flwigevnt daswhen TS<0(‘tail-ke days’) , there is a significant shift in the distribution towards the right, along with higher volatility and skew, compared to “normal days” (Figure 6Subseqnt SpoReurn Distbuon flwigevnt daswhen TS>0(‘normal dys’) when TS is positive. This effect becomes more pronounced as the TS inversion steepens (Figure 7Subseqnt mdiaretuns ofSPXincreas thmruce invrtsep, andlsoicrea wthnor). For example, if the TS is inverted by more than $- 2 \%$ , the median return can reach nearly $3 \%$ just 10D later, compared to a median return of $0 . 1 8 \%$ on “normal days”. Additionally, the return distribution tends to peak more to the right as the tenor increases, suggesting that the longer the time frame, the greater the potential for upside returns.

This suggests that having long delta exposure on days when the TS is inverted could be highly profitable in the following period.

1,5,10,22D post event day

![](images/6b069d16c4c8d66fdf5728f7bc0efe2048bac4c35ae9b86628645512fc39ad0d.jpg)  
Figure 5: Subsequent Spot Return Distribution following event dates when TS <0 (‘tail-like days’)

1,5,10,22D post event day

![](images/5430f0d914c227197f92fcf56894a7b76c1d4b8980113b732094e5e1092ec08b.jpg)  
Figure 6: Subsequent Spot Return Distribution following event dates when TS >0 (‘normal days’)   
Source: Bloomberg Finance L.P., J.P. Morgan Equity Derivatives Strategy

Source: Bloomberg Finance L.P., J.P. Morgan Equity Derivatives Strategy

![](images/9041861757afdb84067b91f5b5f1725b13169ce28cebce6d64e50ef51d57f5f3.jpg)  
Figure 7: Subsequent median returns of SPX increase as the term structure inverts steeper, and also increase with tenor

# Skew

Another interesting observation is that these upside returns are often accompanied by large market moves. On “normal days”, the average realized vol on up days minus down days is negative across all tenors, aligning with the typical left skew observed in the equity vol surface.

However, when the TS is inverted, the upside moves tend to be larger than the downside moves (Figure 8Up dayrelizd vomnusdw ayrelizd vo). This effect is most pronounced for shorter tenors, and becomes more significant with the steepness of the inversion. For example, when the TS inversion exceeds 2 vol points, the realized vol on up days is 2.5 vol higher than on down days, on average for 1W tenor.

![](images/440020a8c22b669c57e40ec81ee44d7157c2a7506f9df3afc2ed8c6b17513eac.jpg)  
Figure 8: Up day realized vol minus down day realized vol   
Source: Bloomberg Finance L.P., J.P. Morgan Equity Derivatives Strategy

![](images/968c53ee52e4f514e88621cb10b8304f6ec7ebae8115a1cce7d76dc965ad4ab7.jpg)  
Figure 9: Implied skew is steeper on TS $_ { < 0 }$ days From 2008, 5D tenor $9 7 . 5 \AA - 1 0 2 . 5 \%$ skew (\~25 delta)   
Source: Bloomberg Finance L.P., J.P. Morgan Equity Derivatives Strategy

Is this effect reflected in the implied volatility surface? No. In fact, we observe the opposite in the implied skew – it actually prices a steeper LEFT tail for days with TS inversion, as the market panics about an acceleration of downside momentum (Figure 9Implied skwtper onTS<0 days). This indicates that short-dated upside implied volatility may be significantly underpriced in the options market.

# Realized Volatility

What about realized volatility following inversion days? The 5 Days preceeding these inversion days exhibited a substantial right tail in the distribution of the realized minus implied vol spread (Figure 10Distrbuon fRealizd mnusIplied Vofr5Dteno psTS<0day).

![](images/898d2b808e20159793d0ed90be83375b6f7a8225f8a13d1ed1abc43abf48b7df.jpg)  
Figure 10: Distribution of Realized minus Implied Vol for 5D tenor post TS <0 day From 2008   
Source: Bloomberg Finance L.P., J.P. Morgan Equity Derivatives Strategy

Given the short tenor, large market moves, such as Mar-20 or Apr-25, resulted in notable increases in realized volatility, surpassing already elevated implied vol levels. This is consistent with the strong relationship between autocorrelation and volatility regimes, which has been discussed in detail by JPM Quant Research in Single Asset Mean Reversion.

![](images/45ebbcb02ffbd17db249c79116c6e8cb140808a5bd61c11060d6eafa59a2a361.jpg)  
Figure 11: Relationship between12M lag-1 autocorrelation and realized volatility   
Source: Bloomberg Finance L.P., J.P. Morgan Equity Derivatives Strategy

The lag-1 autocorrelation becomes significantly more negative in distressed times when volatility is highly elevated. This means very strong close to close mean reversion, suggesting that owning gamma with a delta hedge could deliver very good PnL. Short-dated options have the highest gamma, and the PnL is proportional to the square of realized minus implied vol. Therefore, owning these options can amplify the effect of gamma trading.

# Implied Volatility

What about implied volatility? Unsurprisingly, the VIX tends to spike during times of market distress, but the subsequent normalization can occur quite rapidly, resulting in a strong left-tail return distribution.

![](images/b80a4e9fb479f56bd3452ac952b77a9affd0e40bd343eb16af172f85a0c43491.jpg)  
Figure 12: Subsequent VIX Return Distribution post TS $\scriptstyle < 0$ From 2004 for change in UX1, vertical line at 1M median

![](images/681f6063b1a3bf8ff37006ad0245f6ed29aa5089cf92ce20fe5e70084943050b.jpg)  
Figure 13: Subsequent VIX Return Distribution post TS >0 From 2004 for change in UX1, vertical line at 1M median   
Source: Bloomberg Finance L.P., J.P. Morgan Equity Derivatives Strategy

Source: Bloomberg Finance L.P., J.P. Morgan Equity Derivatives Strategy

This observation is similar to the finding regarding spot returns – the longer the tenor, the stronger the effect of the left skew. Given the high vol of vol, it’s important to select tenors that are short enough to have liquidity but long enough to capture the PnL effect. The 1M tenor is a good choice as it has already demonstrated robust results, with a median value of -3.2 vol points compared to a median value of 0 on “normal days”.

In conclusion, there is a consistent pattern of market behavior following days when the 3M-1M implied volatility term structure inverts, with the effect being more pronounced as the inversion steepens. We summarize the results below in three groups: Spot, Realized Vol (and Skew), and Implied Vol (VIX).

Figure 14: Median spot return, average realized skew and volatility, and median VIX return for different tenors post ‘normal days’ and TS $\mathtt { \Omega } < 0$ days   
From 2004   

<table><tr><td rowspan="2"></td><td colspan="4">TS&lt;O Days 1W</td></tr><tr><td></td><td></td><td>2W</td><td>1M</td></tr><tr><td>Spot Return</td><td>0.1%</td><td>0.7%</td><td>1.2%</td><td>2.2%</td></tr><tr><td>Skew (Up-Down Vol)</td><td></td><td>0.1%</td><td>0.5%</td><td>0.4%</td></tr><tr><td>Realized Vol</td><td></td><td>27.9%</td><td>27.8%</td><td>26.6%</td></tr><tr><td></td><td>2w</td><td></td><td>2M</td><td>3M</td></tr><tr><td>VIXReturn</td><td>-1.92</td><td>-3.15</td><td>-4.1</td><td>-4.76</td></tr></table>

<table><tr><td colspan="4">Normal Days</td></tr><tr><td>1D 1W 0.1%</td><td>2W 0.3%</td><td>0.6%</td><td>1M 1.3%</td></tr><tr><td></td><td>-0.3%</td><td>-0.4%</td><td>-0.9%</td></tr><tr><td></td><td>11.7%</td><td>12.4%</td><td>13.2%</td></tr><tr><td>2w 1M</td><td></td><td>2M</td><td>3M</td></tr><tr><td colspan="2">0</td><td colspan="2">-0.05</td></tr></table>

<table><tr><td rowspan="2">1D</td><td colspan="4">TS&lt; -2 Days</td></tr><tr><td>1W</td><td>2W</td><td></td><td>1M</td></tr><tr><td>Spot Return</td><td>0.2%</td><td>0.6%</td><td>1.8%</td><td>3.0%</td></tr><tr><td>Skew (Up-Down Vol)</td><td></td><td>2.6%</td><td>2.4%</td><td>1.6%</td></tr><tr><td>Realized Vol</td><td></td><td>41.8%</td><td>41.4%</td><td>38.6%</td></tr><tr><td></td><td>2w</td><td>1M</td><td>2M</td><td>3M</td></tr><tr><td>VIX Return</td><td>-2.75</td><td>-4.465</td><td>-7.05</td><td>-9.52</td></tr></table>

Source: Bloomberg Finance L.P., J.P. Morgan Equity Derivatives Strategy

<table><tr><td colspan="4">Normal Days 1W 2W 1M</td></tr><tr><td>1D 0.1%</td><td>0.3%</td><td>0.6%</td><td>1.3%</td></tr><tr><td></td><td>-0.3%</td><td>-0.4%</td><td>-0.9%</td></tr><tr><td></td><td>11.7%</td><td>12.4%</td><td>13.2%</td></tr><tr><td>2w 1M</td><td></td><td>2M</td><td>3M</td></tr><tr><td>0</td><td>0</td><td>-0.05</td><td>-0.05</td></tr></table>

# Three Avenues for Trading Opportunities

The study of behavior in “tail like periods” opens up three avenues for trading opportunities in the Delta, Gamma, and Vega spaces. Here, we explore them in more detail by assuming a notional of $\$ 101 n$ initiated in 2016, as data quality is limited beyond this.

# Profiting from Spot Return in Delta Space

This pressure for spot upside returns can be leveraged by buying futures outright (Delta 1), or long short-dated call options outright.

For using futures, we tested different holding periods from 1D to 1M. The notional is scaled by the tenor (e.g. for 10D tenor, trades involve $10 \%$ of $\$ 101 n$ each time the signal is triggered. This approach ensures that maximum exposure doesn’t exceed $100 \%$ on any given day, even with overlapping trades.)

![](images/15620dd94c37f7cc2998c6c4c1220a1f0ae47ceecd04cc2d468df5a0e9f8e98c.jpg)  
Figure 15: Long Delta on Futures with different holding tenors \$1M/Tenor per trade

Source: Bloomberg Finance L.P., J.P. Morgan Equity Derivatives Strategy   

<table><tr><td></td><td>Max DDDD Date</td><td>Recovery</td><td></td><td>Worst1D Ann Rtn Ann Vol</td><td></td><td>Rtn/Vol</td></tr><tr><td>1D</td><td>-30.2% 20/03/2020</td><td>164</td><td>-10.6%</td><td>3.6%</td><td>14.3%</td><td>0.25</td></tr><tr><td>1W</td><td>-27.2% 20/03/2020</td><td>144</td><td>-9.9%</td><td>5.6%</td><td>13.3%</td><td>0.42</td></tr><tr><td>2W</td><td>-26.3% 20/03/2020</td><td>139</td><td>-9.5%</td><td>5.6%</td><td>12.3%</td><td>0.45</td></tr><tr><td>1M</td><td>-17.8% 20/03/2020</td><td>14</td><td>-7.0%</td><td>6.1%</td><td>10.2%</td><td>0.59</td></tr></table>

Similar to Figure 5Subseqnt SpoReurn Distbuon flwigevnt daswhen TS<0(‘tail-ke days’) , the longer the holding period, the more time we are giving for the market to normalize from the distress, hence the best return for 1M tenor (22 Bdays). By entering only 1/22 notional when TS signal is hit, it acts as an averaging-in effect and increases exposure if sell-off continues to buy at a better level. However, all the futures implementations are subject to very large Max DD.

To play the long delta with options instead, where the max loss is capped at the option premium, we examined ATM and 25 delta calls. Note that, for option strategies, we should take the $\mathrm { R t n } / \mathrm { V o l }$ measure with a pinch of salt given the non-linear behavior. Much of the profit is driven by large “gappy moves” on the upside, which would increase the volatility of the strategy, but for good cause. All call options are scaled down by the tenor-like the futures strategy, but as we only spend premium so could afford some leverage which we used as 3X.

![](images/acddcc8725fa15d514dd40cfa086ce55b5a06d20e6d4bc34116d0d0e0cfe2bbf.jpg)  
Figure 16: Long Delta with ATM Call MTM   
\$1M/Tenor per trade, 3x Leverage

Source: OPRA, J.P. Morgan Equity Derivatives Strategy   

<table><tr><td></td><td>MaxDD DDDate</td><td>Recovery</td><td>Worst 1D</td><td>Ann Rtn</td><td>Ann Vol</td><td>Rtn/Vol</td><td>Hit Ratio</td></tr><tr><td>5DATM</td><td>-30.5% 23/03/2020</td><td>164</td><td>-10.6%</td><td>6.3%</td><td>18.1%</td><td>0.35</td><td>43.3%</td></tr><tr><td>10D ATM</td><td>-17.5% 03/04/2020</td><td>5</td><td>-8.8%</td><td>5.1%</td><td>14.9%</td><td>0.34</td><td>48.6%</td></tr><tr><td>1MATM</td><td>-15.6% 03/01/2019</td><td>176</td><td>-5.9%</td><td>7.0%</td><td>13.4%</td><td>0.52</td><td>57.6%</td></tr></table>

![](images/fbbd5215f555c180be323e1ee6c2f19fef6eaf8f3df43ef1c7d554303b7c0bf0.jpg)  
Figure 17: Long Delta with 25 Delta Strike Call MTM   
\$1M/Tenor per trade, 3x Leverage

Source: OPRA, J.P. Morgan Equity Derivatives Strategy   

<table><tr><td></td><td>Max DD DD Date</td><td></td><td>Recovery</td><td>Worst 1D</td><td>Ann Rtn Ann Vol</td><td></td><td>Rtn/Vol</td><td>Hit Ratio</td></tr><tr><td>5D25D</td><td>-11.4%</td><td>23/03/2020</td><td>4</td><td>-7.8%</td><td>2.9%</td><td>9.6%</td><td>0.30</td><td>27.3%</td></tr><tr><td>10D25D</td><td>-10.3%</td><td>03/04/2020</td><td>5</td><td>-5.9%</td><td>2.3%</td><td>9.0%</td><td>0.26</td><td>33.7%</td></tr><tr><td>1M25D</td><td>-8.8%</td><td>09/11/2022</td><td>654</td><td>-3.9%</td><td>1.8%</td><td>6.7%</td><td>0.26</td><td>32.2%</td></tr></table>

The outright long ATM calls have delivered significantly better PnL compared to 25 delta calls as the “hurdle” to go above strike plus premium was more demanding on the 25d. Longer tenors have outperformed marginally too, for reasons similar to the future strategy, allowing higher PnL and smaller Max DD.

With these findings, call spreads could be a good solution as they also reduce the premium significantly given the elevated cost of vol in a market in distress. 1M ATM-25 Delta Call Spread indeed delivered a much better worst 1D and MDD than the ATM calls, while giving up little on the return.

# 1M ATM-25d CS

<table><tr><td></td><td>Max DD</td><td>DD Date</td><td>Recovery</td><td>Worst 1D</td><td>Ann Rtn Ann Vol</td><td></td><td>Rtn/Vol</td><td>Hit Ratio</td></tr><tr><td>S</td><td>-10.3%</td><td>02/01/2019</td><td>330</td><td>-3.3%</td><td>5.1%</td><td>7.5%</td><td>0.67</td><td>62.2%</td></tr></table>

![](images/c045e383b90912bb295f6d3b68bd5ebde1245d5e24b3d3cbe061da919fc84f0c.jpg)  
Figure 18: Long 3x 1M Call Spread MTM   
Notional 1/22 per trade   
Source: OPRA, J.P. Morgan Equity Derivatives Strategy

Note that we are holding all trades to maturity for simplicity, whereas in reality calls should be unwound and rolled when options are deep in the money. This can potentially enhance the performance further.

# Profiting from Realized Vol and Upside Skew in Gamma Space

The next avenue of $\mathrm { P n L }$ is generated from the underpricing of realized vol, particularly on the upside strikes, confirmed by the backtest results of delta hedged calls. Shorterdated options deliver better results, in general, as the size of the gamma is the largest at this tenor. In terms of strikes, 25 Delta strikes delivered better than ATM as spot gaps up and stayed volatile around the upside. PnL starts to drift lower with longer tenors as volatility starts normalizing post spot consolidation. Therefore, within our iterations, 5D tenor 25 Delta Call hedged daily at the close produced the most robust results.

![](images/69ac1ad8b43a60717c56a1c093652756b88612bc793d2fa2764e162448dc51e8.jpg)  
Figure 19: Delta Hedged Call for ATM Strike MTM   
Assume $\$ 10$ notional per trade, including overlaps Source: OPRA, J.P. Morgan Equity Derivatives Strategy

![](images/f19ae488ab45c804040a3d83e773e8c2c0314b4a7ca8e7d630ec41b11a8748a6.jpg)  
Figure 20: Delta Hedged Call for 25 Delta Strike MTM   
Assume $\$ 10$ notional per trade, including overlaps Source: OPRA, J.P. Morgan Equity Derivatives Strategy

In addition to the previous discussion of up days outdelivering down days vol (Figure 8Up dayrelizd vomnusdw ayrelizd vol), the autocorrelation also helps to explain the behavior in distressed periods (Figure 21Autocrelain ofSPXbetwn F-Ju20). The lag-1 is strongly negative while lag-2 is strongly positive, suggesting a flip-flop of direction daily, which is the ideal set up for long gamma trading. This is much less if we run the data over a longer period covering mostly “normal days” (Figure 22Autocrelain ofSPXrm 195).

![](images/0c4ce42331bf3a2d0921d90802bf6748a815d1a1517891fa4e7f2060b02a6071.jpg)  
Figure 21: Autocorrelation of SPX between Feb-Jun 2020 Lag1 $= - 0 . 4 1$ , $\mathsf { L a g 2 } = 0 . 3$

Source: Bloomberg Finance L.P., J.P. Morgan Equity Derivatives Strategy

![](images/af8d77dcf6e0f1662f2cc47f4a86a3e1c9322b06bf4a6a42fbcbbbcef80cddd8.jpg)  
Figure 22: Autocorrelation of SPX from 1995 Lag1 = -0.09, Lag2 =0   
Source: Bloomberg Finance L.P., J.P. Morgan Equity Derivatives Strategy

When a large gap move occurs, the gamma PnL can be significant due to the square effect, causing the distribution of the $\mathrm { P n L }$ per trade to have an excessive right tail.

![](images/0662301b0dc9cbe4427f3f813d469db3e5d1cf67316233296911a8c71af59004.jpg)  
Figure 23: Distribution of PnL from Delta Hedged Call of 25d Strike 5D Tenor   
Source: OPRA, J.P. Morgan Equity Derivatives Strategy

Another interesting observation during market distress is the “V-Shape” relationship of the PnL of delta-hedged and unhedged short-dated options. This means that, while owning the call outright delivers very good PnL, the delta hedged version usually did well too, as the “gap up” effect delivers gamma PnL. However, when the “buy-on-dip” didn’t work (long call outright was negative), this is when long delta-hedged call delivered great PnL, with some outstanding results on the upside. The reason being, when outright long calls don't work, it's most likely when momentum has accelerated on the downside. This is usually accompanied by even larger panic moves and further increases in volatility, producing solid gamma PnL.

![](images/8c0aac6a0e8f71801e05954a2d2ed52efe61f239330441d7033f11791f0f68ac.jpg)  
Figure 24: PnL per Trade ATM Call 5D Tenor x-long call outright, y- long call delta hedged

![](images/89f0381148234f3c1b55f0206a9c5a3efb34b99939c65d3e54db85f6868b38ee.jpg)  
Figure 25: PnL per Trade for 25 Delta Call 5D Tenor x- long call outright, y- long call delta hedged

Trade when $\scriptstyle \mathsf { T S } > 0$ from 2008, prior 2016 less data point Source: OPRA, J.P. Morgan Equity Derivatives Strategy

# Profiting from Normalization in the VIX in Vega Space

The third avenue of profit is from the normalization of implied volatility after the distress. We saw how $\mathrm { P n L }$ started to drop as tenor increases for the gamma trade in Figure 19 and Figure 20. This effect could be well capitalized with a short implied vol trade and hedge the gamma trade PnL to some extent.

VIX is a good liquid instrument to use, where one can sell implied vol in a safe way via owning put options. As previous findings suggest that 1-2M is usually the length it takes to retrace the initial shock (Figure 12Subseqnt VIXReurn Distbuon pstTS<0), we investigated holding futures as well as VIX put options for different tenors.

We trade whenever UX1 is higher than UX3. For the futures implementation, we enter a short 1 unit of UX1 future and hold for 1D-1M tenors, scaled by the tenor (e.g. 1M tenor short 1/22 futures on trade day held for 22 days).

![](images/db496d204ed7e4061e773ab6ff7f250463b3253c7e3bed43d09cab034a0969e6.jpg)  
Figure 26: Short VIX with UX1 Futures with different holding tenors   
PnL in Vol points (VIX future value PL)

Source: Bloomberg Finance L.P., J.P. Morgan Equity Derivatives Strategy   

<table><tr><td></td><td>1D</td><td>1W</td><td>2W</td><td>1M</td><td></td></tr><tr><td>Avg Rtn</td><td>7.1</td><td></td><td>7.9</td><td>7.5</td><td>6.7</td></tr><tr><td>MDD</td><td>52.6</td><td>1</td><td>49.3</td><td>45.9</td><td>28.2</td></tr></table>

The result did deliver around 7 points of PnL per year on average, but the drawdown can be extremely large due to the high vol of vol.

Therefore, this alpha is best captured with put option structures. We tested the listed expiries closest to the tenors below for different strikes.

Figure 27: Buy VIX Put on TS $_ { < 0 }$ dates and hold to maturity, average Premium and PL per trade From 2016   

<table><tr><td rowspan="2"></td><td colspan="3">ATM</td><td colspan="3">25D</td><td colspan="3">10D</td></tr><tr><td>Hit Ratio</td><td>Avg Prem</td><td>Avg PL</td><td>HitRatio</td><td>Avg Prem Avg PL</td><td></td><td>Hit Ratio Avg Prem Avg PL</td><td></td><td></td></tr><tr><td>1w</td><td>43%</td><td>3.14</td><td>-0.28</td><td>26%</td><td>0.99</td><td>-0.28</td><td>12%</td><td>0.29</td><td>-0.11</td></tr><tr><td>1M</td><td>60%</td><td>5.32</td><td>0.82</td><td>39%</td><td>1.57</td><td>0.01</td><td>19%</td><td>0.44</td><td>-0.17</td></tr><tr><td>2M</td><td>74%</td><td>6.12</td><td>2.27</td><td>48%</td><td>1.76</td><td>0.66</td><td>33%</td><td>0.47</td><td>0.27</td></tr><tr><td>3M</td><td>81%</td><td>6.42</td><td>2.09</td><td>51%</td><td>1.83</td><td>0.57</td><td>28%</td><td>0.48</td><td>0.10</td></tr></table>

Source: OPRA, J.P. Morgan Equity Derivatives Strategy

Similar to using call spreads to go long delta, given the elevated vol of vol, put spreads are a much better solution than owning outright puts. Buying OTM puts can also be challenging as the implied vol is likely to remain elevated keeping the payout at zero, hence wasting the premium. However, we can use very OTM puts as a funding leg: the 10 Delta puts still give 0.44 vol of average premium credit while the hit ratio is low.

Therefore, a 1M ATM-25d-10d put ladder would be a good implementation to take advantage of the vol of vol and the floor on implied volatility post market distress. To make the sizing more realistic, we also scale down the notional by the tenor, in this case an average of 26 days. The max drawdown is -2.5 vol points with this set up.

![](images/5f68e7b2dd7fa6a18c35460d2e6e0d5ece2ee34cc89d16a16e8dfa1e9838d1b8.jpg)  
Figure 28: Long ATM -25d-10d Put Ladder on VIX for the closest to 1M expiry MTM Notional 1/26 per trade

# Three Pillar Framework for PnL Delivery

As these three avenues of trading opportunities play in different spectrums of the Greeks, they have somewhat of a hedging and diversifying effect among themselves.

We saw the “V-shape” PnL relationship between long delta and long gamma trades (Figure 24PnL perTadAM Cl5DTenor). The VIX leg also provides some PnL offset to the gamma trade, as it tends to deliver when the market stabilizes a bit, which often happens when gamma PnL underperforms (Figure 29Long 1MVIXPut Ladervsu DltaHedg 25DTECal).

![](images/70c31078cf6e4e6c35725619d16bda5edde1b825c7bbf6f8caf731341a645269.jpg)  
Figure 29: Long 1M VIX Put Ladder versus Delta Hedged 25d 5DTE Call Pnl Per Trade, x-axis pnl of delta hedge call, y-axis VIX unscaled

Source: OPRA, J.P. Morgan Equity Derivatives Strategy

![](images/fefc1cba5411a1cd339526aa2aa5c3e74dcee6b16f3268ef2b48f8c251bd8c6b.jpg)  
Figure 30: Long 1M VIX Put Ladder versus 1M ATM-25 Call Spread Pnl Per Trade, x-axis pnl of delta hedge call, y-axis VIX unscaled   
Source: OPRA, J.P. Morgan Equity Derivatives Strategy

However, the VIX trades have a slightly positive relationship with the long delta trades (Figure 30Long 1MVIXPut Ladervsu 1MAT-25 CalSpred), making the gamma trade the most “diversifying” leg of the three.

We therefore constructed a framework with three pillars for a more balanced strategy to deliver PnL.

![](images/0ca37fff5098b36b9ab0ac9102b1760754e4faed724ae7c2f6fa07d65e4e88ef.jpg)

In terms of sizing, here is the thought process:

1. Delta Trade: Buy SPX 1M ATM-25D call spread scaled by tenor (1/22) per trade. We used $\mathbf { 3 x }$ leverage on this to have a decent delta exposure without excessive potential waste in premium. This leg could be reduced depending on risk appetite, while dynamic rolling could improve delivery too.

2. Gamma Trade: Buy SPX 5D 25 Delta Call options with daily hedging on the close, full notional per trade each time the signal triggers. This means one can have up to $5 \mathbf { x }$ notional on a given day if the signal triggers for five consecutive days. However, these options would likely have different strike prices and cover a good range of gamma exposure, which we like. Also, as this leg is the most “diversifying” of the three pillars, we like having more weight in this, especially since it’s flat net delta with very low worst PnL.

3. Vega Trade: Buy VIX 1M ATM-25d-10d Put Ladder scaled by tenor (1/26) per trade. For the sizing in VIX, we match around the vega of the delta-hedged leg, which is around $0 . 0 4 \%$ per trade.

The final portfolio resulted in the following back test, which captured especially robust positive PnL in periods of market distress in 2020, 2022, 2024 and 2025.

Tail Trading Strategy

<table><tr><td>Return</td><td>Volatility</td><td>Rtn/Vol</td><td>Worst 1D</td><td>MaxDD</td></tr><tr><td>10.53%</td><td>10.56%</td><td>1.00</td><td>-3.27%</td><td>-9.67%</td></tr></table>

![](images/b4e5dcf7cf78ae4029d43f374fb1be69974ca59b75ed8a00e75b25f9a1bc5802.jpg)  
Figure 31: PnL of the Tail Trading Strategy   
Source: OPRA, J.P. Morgan Equity Derivatives Strategy

![](images/b5cdbb2248d00fb18d2783ed45dea3c88de79109c7ac9901966024ab11641724.jpg)  
Figure 32: Contribution of PnL by Strategy   
Source: OPRA, J.P. Morgan Equity Derivatives Strategy

A feature we like particularly on the construction of this tail-trading strategy is that the max loss is almost entirely defined upfront – the investor is almost always buying options.

The delta trade is buying call spreads, the gamma trade is buying short-dated options and hedging, while the vol trade is buying put structure on VIX. Only the VIX leg has a risk of going through the short 10 delta strike. However, we looked at all the negative PnL cases and found that only $1 5 \%$ of the negative cases were from the short 10d put going through the strike with an average loss of 0.8 vols in those cases, whereas “waste of premium” accounted for $8 5 \%$ with an average loss of 1.9 vols. The weighting and, hence, the contribution from the VIX leg is also smaller than the other two which minimizes this issue further (Figure 32Contribu ofPnLby Straegy).

# Useful Applications in Practice

The findings above can serve as a standalone addition to diversifying investment portfolios. Due to the unique periods and avenues of PnL delivery, we want to highlight two particular useful applications.

# Overlay to Systematic Hedging Strategies in Equity

We recently conducted a deep dive on hedging strategies and explored methods to improve their effectiveness while minimizing drag. Regardless of the optimization method, two key issues still remain:

1. The cost of having protection will always be a drag, methods to reduce it usually result in less PnL from protection too

2. Trying to lock in profits from protection can be challenging. If protection is sold for profit capture, new protection could be expensive to roll into.

However, with the new tail-trading strategy, it solves both issues in a robust manner. During periods with no tail-like events, no premium is paid, hence no drag at all. When a tail event happens, the systematic put hedges start to work, and the tail-trading strategy delivers robust subsequent PnL. This means existing hedges can still be kept in place as profit-taking from the hedge is effectively done via the tail-trading strategy.

![](images/a6c410b9c40f17bc68daee7bf66304364aaef56398249afe506fed387c114e10.jpg)  
Figure 33: SPX Put hedging strategies compared with Tail- trading   
Long 3M 30d put or 30d-10d put spread, rolled 1M into the trade Source: Bloomberg Finance L.P., J.P. Morgan Equity Derivatives Strategy

![](images/df76301f656ec19adac9ef572eb590f8ac7a818d241087095d81b1a9aecd4f3b.jpg)  
Figure 34: SPX Put or Put spread strategies combined with Tail-trading   
Long 3M 30d put or 30d-10d put spread, rolled 1M into the trade Source: Bloomberg Finance L.P., J.P. Morgan Equity Derivatives Strategy

We see a nice “relay” of PnL delivery between the traditional systematic put strategies and the tail-trading strategy at each tail event (Figure 33SPX uthedgin straegi compared withTal- rding). If we combine the two, the put systematic strategy delivers sharp protection as a sell-off starts, while the tailtrading strategy captures the gains and delivers robust subsequent profits.

Figure 35: Yearly Returns for Systematic Put Hedging Strategies, Tail-Trading Strategy, and the ‘combo’ of Systematic Put Spread $^ +$ Tail-Trading   

<table><tr><td rowspan=2 colspan=1>2016</td><td rowspan=1 colspan=4>PS-C      Collar    PS        Put</td><td rowspan=1 colspan=1>TailTrading</td><td rowspan=1 colspan=1>PS+Tail</td></tr><tr><td rowspan=1 colspan=2>-5.8%     -9.3%</td><td rowspan=1 colspan=2>-3.87%     -7.4%</td><td rowspan=1 colspan=1>7.5%</td><td rowspan=1 colspan=1>3.6%</td></tr><tr><td rowspan=1 colspan=1>2017</td><td rowspan=1 colspan=1>-6.8%</td><td rowspan=1 colspan=1>-9.6%</td><td rowspan=1 colspan=2>-4.58%     -7.4%</td><td rowspan=1 colspan=1>0.4%</td><td rowspan=1 colspan=1>-3.8%</td></tr><tr><td rowspan=2 colspan=1>20182019</td><td rowspan=1 colspan=1>2.8%</td><td rowspan=1 colspan=1>2.8%</td><td rowspan=1 colspan=2>3.10%      3.2%</td><td rowspan=1 colspan=1>-4.4%</td><td rowspan=1 colspan=1>-2.1%</td></tr><tr><td rowspan=1 colspan=1>-10.7%</td><td rowspan=1 colspan=1> -13.8%</td><td rowspan=1 colspan=1>-5.20%</td><td rowspan=1 colspan=1>-8.4%</td><td rowspan=1 colspan=1>11.6%</td><td rowspan=1 colspan=1>7.2%</td></tr><tr><td rowspan=1 colspan=1>2020</td><td rowspan=1 colspan=1>1.0%</td><td rowspan=1 colspan=1>9.8%</td><td rowspan=1 colspan=2>-4.84%      3.6%</td><td rowspan=1 colspan=1>45.8%</td><td rowspan=1 colspan=1>46.1%</td></tr><tr><td rowspan=2 colspan=1>20212022</td><td rowspan=1 colspan=1>-11.2%</td><td rowspan=1 colspan=1>-15.5%</td><td rowspan=1 colspan=2>-6.34%   -10.9%</td><td rowspan=1 colspan=1>0.0%</td><td rowspan=1 colspan=1>-3.3%</td></tr><tr><td rowspan=1 colspan=2>1.9%      0.3%</td><td rowspan=1 colspan=2>3.77%      2.2%</td><td rowspan=1 colspan=1>10.8%</td><td rowspan=1 colspan=1>14.3%</td></tr><tr><td rowspan=1 colspan=1>2023</td><td rowspan=1 colspan=1>-6.3%</td><td rowspan=1 colspan=1>-9.3%</td><td rowspan=1 colspan=1>-3.85%</td><td rowspan=1 colspan=1>-6.9%</td><td rowspan=1 colspan=1>-0.5%</td><td rowspan=1 colspan=1>-2.4%</td></tr><tr><td rowspan=2 colspan=1>20242025</td><td rowspan=1 colspan=1>-8.7%</td><td rowspan=1 colspan=1>-11.1%</td><td rowspan=1 colspan=2>-3.83%     -6.3%</td><td rowspan=1 colspan=1>3.0%</td><td rowspan=1 colspan=1>1.5%</td></tr><tr><td rowspan=1 colspan=4>-4.4%     -4.1%    0.44%     0.8%</td><td rowspan=1 colspan=1>6.5%</td><td rowspan=1 colspan=1>7.6%</td></tr></table>

Source: Bloomberg Finance L.P., J.P. Morgan Equity Derivatives Strategy

For SPX long-only portfolio, we find superior results with much better Sharpe and worst DD when we overlay this “combo hedge”, which consists of both the Tail-Trading Strategy and the Systematic Put Spread strategy. Since the base portfolio is long SPX already, we switch off delta on SPX long portfolio when TS ${ < } 0$ signal is hit to avoid too much excess delta exposure as the tail strategy already has a long delta bias.

Figure 36: Combo-hedge: Tail-Trading strategy combined with Systematic Put Spread returns by month   

<table><tr><td></td><td>1</td><td>2</td><td>3</td><td>4</td><td>5</td><td>6</td><td>7</td><td>8</td><td>9</td><td>10</td><td>11</td><td>12</td></tr><tr><td>2016</td><td>4.1%</td><td>0.1%</td><td>-0.3%</td><td>0.0%</td><td>-0.3%</td><td>1.6%</td><td>0.0%</td><td>-0.2%</td><td>-0.1%</td><td>0.1%</td><td> -1.1%</td><td> -0.4%</td></tr><tr><td>2017</td><td>-0.4%</td><td>-0.6%</td><td>-0.2%</td><td>-0.4%</td><td>-0.4%</td><td>-0.1%</td><td>-0.5%</td><td>0.3%</td><td>-0.4%</td><td>-0.3%</td><td>-0.4%</td><td>-0.3%</td></tr><tr><td>2018</td><td>-0.2%</td><td> 1.8%</td><td>-0.5%</td><td> -2.1%</td><td>0.7%</td><td>0.2%</td><td>-0.9%</td><td>-0.6%</td><td>-0.3%</td><td>2.6%</td><td>1.4%</td><td>-4.1%</td></tr><tr><td>2019</td><td>3.5%</td><td>0.2%</td><td>-0.5%</td><td>-0.5%</td><td>-0.5%</td><td>1.4%</td><td>0.0%</td><td>4.9%</td><td>1.5%</td><td>-0.5%</td><td>-0.4%</td><td>-0.7%</td></tr><tr><td>2020</td><td>0.3%</td><td>2.6%</td><td>19.6%</td><td>15.5%</td><td>5.7%</td><td>-3.5%</td><td>1.8%</td><td>-0.5%</td><td>0.3%</td><td>-0.5%</td><td>3.5%</td><td>-0.1%</td></tr><tr><td>2021</td><td>0.0%</td><td>-0.6%</td><td>-0.5%</td><td>-0.2%</td><td>-0.4%</td><td>-0.3%</td><td>-0.1%</td><td>-0.4%</td><td>0.6%</td><td>-0.7%</td><td>0.0%</td><td>-0.2%</td></tr><tr><td>2022</td><td>0.6%</td><td>-2.2%</td><td>3.6%</td><td>2.9%</td><td>6.2%</td><td> -2.6%</td><td>0.0%</td><td>0.3%</td><td>0.6%</td><td>3.7%</td><td>1.0%</td><td>0.6%</td></tr><tr><td>2023</td><td>-0.7%</td><td>-0.4%</td><td>-0.4%</td><td>-0.1%</td><td>-0.3%</td><td>-0.4%</td><td>-0.3%</td><td>-0.1%</td><td>0.6%</td><td>-0.5%</td><td>0.5%</td><td>-0.3%</td></tr><tr><td>2024</td><td>-0.2%</td><td>-0.3%</td><td>-0.2%</td><td>-0.1%</td><td>0.2%</td><td>-0.2%</td><td>0.1%</td><td>2.0%</td><td> -1.2%</td><td> -2.4%</td><td>3.6%</td><td>0.1%</td></tr><tr><td>2025</td><td>0.7%</td><td>0.5%</td><td>-1.5%</td><td>4.7%</td><td>2.5%</td><td></td><td></td><td></td><td></td><td></td><td></td><td></td></tr></table>

Source: Bloomberg Finance L.P., J.P. Morgan Equity Derivatives Strategy

![](images/1cd9f48e1f0e615e4dcff77f1b631c9e410615b025118f6f9d56d79c0a21ac5b.jpg)  
Figure 37: Long SPX $^ +$ Put Spread $^ +$ Tail Trading   
Source: Bloomberg Finance L.P., J.P. Morgan Equity Derivatives Strategy

Figure 38: Long SPX with different hedging overlay   

<table><tr><td>SPX</td><td>SPX+PS</td><td>SPX+Tail</td><td>SPX+Tail+PS</td></tr><tr><td>12.5%</td><td>10.2%</td><td>19.4%</td><td>17.1%</td></tr><tr><td>18.2%</td><td>14.8%</td><td>17.3%</td><td>15.4%</td></tr><tr><td>0.69</td><td>0.69</td><td>1.13</td><td>1.11</td></tr><tr><td>-12.0%</td><td>-10.6%</td><td>-5.9%</td><td>-5.0%</td></tr><tr><td>-38.2%</td><td>-31.8%</td><td>-20.6%</td><td>-17.6%</td></tr></table>

# Overlay to SPX CTA Style Trend Following

CTA trend following positions in assets according to the momentum of price returns and usually normalizes the weights by volatility. This performance can be challenging in periods if high vols are accompanied by sharp mean reversion. We examined the time series of SPX leg only using the method in the cross asset trend following strategy.

In periods of peaceful trending markets like 2017-18, 2021, parts of 2023 and 1H24, the trend strategy delivered solid returns. The tail-trading strategy didn’t have much interference as there was zero drag to the portfolio.

However, for periods post the market distress in 2020, 2022, 2H24 and 1H25, the trend strategy gave back some sizable returns as equity exposure started to reduce with spot turning negative on high volatility. The tail-trading strategy, on the other hand, delivered nice complementing returns accordingly in those periods.

![](images/ca87100501567e7b383e01a8ba956fe57be7f53f0543beb6c44e6aa31c13c37e.jpg)  
Figure 39: Tail Trading Strategy Complements SPX Trend Strategy   
Source: Bloomberg Finance L.P., J.P. Morgan Equity Derivatives Strategy

![](images/fb64c8ae86b5e1a31d3149c14b3ebca56cdf8f548412636b59f1dd1184e32609.jpg)  
Figure 40: Performance of Tail Trading $^ +$ SPX Trend combined   
Source: Bloomberg Finance L.P., J.P. Morgan Equity Derivatives Strategy

Overlaying a classic put spread in fact reduced the Sharpe ratio for the portfolio, although it delivered a slightly lower worst 1D loss. Combining trend with tail trading delivered the best return and Sharpe, while the “combo hedge” cut off the worst 1D loss and lowered the Max DD too.

![](images/606fa93c50ead0285293eed204f2cec820d64a3f92151d71bf92babeff8cee95.jpg)  
Figure 41: Trend on SPX $^ +$ Put Spread $^ +$ Tail Trading   
Source: Bloomberg Finance L.P., J.P. Morgan Equity Derivatives Strategy

Figure 42: SPX Trend with different hedging overlay   

<table><tr><td>Trend</td><td>Trend+PS</td><td>Trend+Tail</td><td>Trend+Tail+PS</td></tr><tr><td>4.7%</td><td>2.4%</td><td>15.1%</td><td>12.8%</td></tr><tr><td>10.6%</td><td>9.4%</td><td>15.2%</td><td>13.5%</td></tr><tr><td>0.45</td><td>0.26</td><td>1.00</td><td>0.95</td></tr><tr><td>-7.1%</td><td>-6.3%</td><td>-6.6%</td><td>-5.8%</td></tr><tr><td>-27.1%</td><td>-28.7%</td><td>-25.1%</td><td>-23.3%</td></tr></table>

# Other Considerations

The current signal we use, based on 3M-1M term structure inversion, is very robust for identifying “tail-like” periods. However, even within this framework, there are days when the inversion becomes more severe, as panic accelerates. These times can deliver even stronger results (Figure 14Median spotreun, avrgelizd skewand voltiy, andmeiVIX rtunfodiert nosp‘rmal dys’nTS <0days). Therefore, one can adjust their weights according to the signal’s strength, taking into account the behavior of other positions within their own portfolios.

For the delta trade, the term structure signal serves as a fairly “strict” metric to identify potential buying opportunities. By lowering the threshold, we could potentially identify more trades. Additionally, there are more techniques to improve the delivery of this leg, such as profit-taking/rolling early when the delta approaches $100 \%$ . We can also employ more signals to dynamically adjust the weighting of the delta trade, such as reducing this leg during a prolonged recessionary bear market, while increasing the weight in a more “flash crash” situation.

The bottom line is, when a tail event happens, don’t be afraid. This is when great trading opportunities open up, offering the potential to double your money with welljudged positions.

# Reality Check on Tail-Period Liquidity

To ensure the backtest is realistic, we use the entry level derived from the premium of the last trade value that occurred in the final $1 5 \mathrm { { m i n } }$ of the trading day for the contract with the specific tenor and has the closest expiry and delta, hence this approaches already accounts forbid-offer costs. Based on the entry levels, the traded prices generally appear to be above the midpoint of NBBO at trade inception, indicating a likely buying interest, which is expected in a sell-off environment.

Since many of these trades are executed under more distressed market conditions, we conducted a reality check on liquidity to assess the worst-case scenario regarding the bid-offer spread.

5D, 10D, 22D Tenor (absolute spread scaled by close spot %)

![](images/a2c39324a705851d9dbe326d7c459c5c69a73a56b0ffda7cb34a3585ab8d7cfa.jpg)  
Figure 43: Bid-Offer Spread for ATM strikes   
Source: OPRA, J.P. Morgan Equity Derivatives Strategy   
Figure 43Bid-Ofer Spadfor ATMstike and Figure 44Bid-Ofer Spadfor 25DStikes show the average bid-offer spread for ATM and 25D options throughout the trading day, scaled by the closing spot price. Overall, liquidity has been improving since 2017. For the ultra-short tenors, such as 5DTE, the bid-offer cost has dropped significantly since the introduction of 0DTE in 2022.

![](images/fdaf10e3e5e982dbd83a3fc408acc6f7c7c7042559d37c8c502ed4eb36533f0b.jpg)  
Figure 44: Bid-Offer Spread for 25D Strikes   
Source: OPRA, J.P. Morgan Equity Derivatives Strategy

25D options have a slightly smaller spread than ATM due to smaller vega risk. The bidoffer spread tends to widen during periods when TS signals are less than 0; however, the average increase is not substantial. Even on days with the worst liquidity, the bid-offer size remains manageable, ensuring that the contracts are still sufficiently liquid for trading.

Figure 45: Bid/Offer Spread in ‘Normal Days’ Absolute Spread Scaled by Close Spot %   

<table><tr><td rowspan=1 colspan=1></td><td rowspan=1 colspan=2>Average B/O</td><td rowspan=1 colspan=2>WorstB/O</td></tr><tr><td rowspan=1 colspan=1>DaystoExp25D</td><td rowspan=1 colspan=1>25D</td><td rowspan=1 colspan=1>50D</td><td rowspan=1 colspan=1>25D</td><td rowspan=1 colspan=1>50D</td></tr><tr><td rowspan=1 colspan=1>5</td><td rowspan=1 colspan=1>0.008%</td><td rowspan=1 colspan=1>0.011%</td><td rowspan=1 colspan=1>0.034%</td><td rowspan=1 colspan=1>0.060%</td></tr><tr><td rowspan=1 colspan=1>10</td><td rowspan=1 colspan=1>0.009%</td><td rowspan=1 colspan=1>0.013%</td><td rowspan=1 colspan=1>0.033%</td><td rowspan=1 colspan=1>0.051%</td></tr><tr><td rowspan=1 colspan=1>22</td><td rowspan=1 colspan=1>0.011%</td><td rowspan=1 colspan=1>0.015%</td><td rowspan=1 colspan=1>0.045%</td><td rowspan=1 colspan=1>0.065%</td></tr></table>

metrics include data from 2018 onwards Source: OPRA, J.P. Morgan Equity Derivatives Strategy

Figure 46: Bid/Offer Spread in TS <0 Days Absolute Spread Scaled by Close Spot %   

<table><tr><td rowspan=1 colspan=1></td><td rowspan=1 colspan=2>Average B/O</td><td rowspan=1 colspan=2>Worst B/O</td></tr><tr><td rowspan=1 colspan=1>DaystoExp25D</td><td rowspan=1 colspan=1>25D</td><td rowspan=1 colspan=1>50D</td><td rowspan=1 colspan=1>25D</td><td rowspan=1 colspan=1>50D</td></tr><tr><td rowspan=1 colspan=1>5</td><td rowspan=1 colspan=1>0.014%</td><td rowspan=1 colspan=1>0.018%</td><td rowspan=1 colspan=1>0.076%</td><td rowspan=1 colspan=1>0.079%</td></tr><tr><td rowspan=1 colspan=1>10</td><td rowspan=1 colspan=1>0.015%</td><td rowspan=1 colspan=1>0.021%</td><td rowspan=1 colspan=1>0.069%</td><td rowspan=1 colspan=1>0.267%</td></tr><tr><td rowspan=1 colspan=1>22</td><td rowspan=1 colspan=1>0.019%</td><td rowspan=1 colspan=1>0.023%</td><td rowspan=1 colspan=1>0.072%</td><td rowspan=1 colspan=1>0.076%</td></tr></table>

metrics include data from 2018 onwards Source: OPRA, J.P. Morgan Equity Derivatives Strategy

# Appendix

# Past Related Publications

Deep Dive on Index Call Strategies Reloading Hedges Amid Rapid Volatility Normalization A Conditional Tactical Rebound Systematic Strategies for the Risk-Off Time Puts vs Defensive Trend-Following Designing robust trend-following system

# Past Highlights from Equity Volatility Strategy

Dispersion Update, Index Technique, Stock Leg and What Now A Practical Dispersion Trading Handbook Trading US macro events with short-dated options The case for long dated Upvar

Analyst Certification: The Research Analyst(s) denoted by an “AC” on the cover of this report certifies (or, where multiple Research Analysts are primarily responsible for this report, the Research Analyst denoted by an “AC” on the cover or within the document individually certifies, with respect to each security or issuer that the Research Analyst covers in this research) that: (1) all of the views expressed in this report accurately reflect the Research Analyst’s personal views about any and all of the subject securities or issuers; and (2) no part of any of the Research Analyst's compensation was, is, or will be directly or indirectly related to the specific recommendations or views expressed by the Research Analyst(s) in this report. For all Korea-based Research Analysts listed on the front cover, if applicable, they also certify, as per KOFIA requirements, that the Research Analyst’s analysis was made in good faith and that the views reflect the Research Analyst’s own opinion, without undue influence or intervention.

All authors named within this report are Research Analysts who produce independent research unless otherwise specified. In Europe, Sector Specialists (Sales and Trading) may be shown on this report as contacts but are not authors of the report or part of the Research Department.

# Important Disclosures

Company-Specific Disclosures: Important disclosures, including price charts and credit opinion history tables (if applicable), are available for compendium reports and all J.P. Morgan–covered companies, and certain non-covered companies, by visiting https://www.jpmm.com/research/disclosures, calling 1-800-477-0406, or e-mailing research.disclosure.inquiries@jpmorgan.com with your request.

# Explanation of Equity Research Ratings, Designations and Analyst(s) Coverage Universe:

J.P. Morgan uses the following rating system: Overweight (over the duration of the price target indicated in this report, we expect this stock will outperform the average total return of the stocks in the Research Analyst’s, or the Research Analyst’s team’s, coverage universe); Neutral (over the duration of the price target indicated in this report, we expect this stock will perform in line with the average total return of the stocks in the Research Analyst’s, or the Research Analyst’s team’s, coverage universe); and Underweight (over the duration of the price target indicated in this report, we expect this stock will underperform the average total return of the stocks in the Research Analyst’s, or the Research Analyst’s team’s, coverage universe. NR is Not Rated. In this case, J.P. Morgan has removed the rating and, if applicable, the price target, for this stock because of either a lack of a sufficient fundamental basis or for legal, regulatory or policy reasons. The previous rating and, if applicable, the price target, no longer should be relied upon. An NR designation is not a recommendation or a rating. In our Asia (ex-Australia and ex-India) and U.K. small- and mid-cap Equity Research, each stock’s expected total return is compared to the expected total return of a benchmark country market index, not to those Research Analysts’ coverage universe. If it does not appear in the Important Disclosures section of this report, the certifying Research Analyst’s coverage universe can be found on J.P. Morgan’s Research website, https://www.jpmorganmarkets.com.

J.P. Morgan Equity Research Ratings Distribution, as of April 05, 2025   

<table><tr><td></td><td>Overweight (buy)</td><td>Neutral (hold)</td><td>Underweight (sell)</td></tr><tr><td>J.P.Morgan Global Equity Research Coverage*</td><td>50%</td><td>37%</td><td>13%</td></tr><tr><td>IB clients** JPMS Equity Research Coverage*</td><td>51%</td><td>49%</td><td>37%</td></tr><tr><td></td><td>47%</td><td>40%</td><td>13%</td></tr><tr><td>IB clients**</td><td>74%</td><td>69%</td><td>52%</td></tr></table>

\*Please note that the percentages may not add to $1 0 0 \%$ because of rounding.

\*Percentage of subject companies within each of the "buy," "hold" and "sell" categories for which J.P. Morgan has provided vestment banking services within the previous 12 months.

For purposes of FINRA ratings distribution rules only, our Overweight rating falls into a buy rating category; our Neutral rating falls into a hold rating category; and our Underweight rating falls into a sell rating category. Please note that stocks with an NR designation are not included in the table above. This information is current as of the end of the most recent calendar quarter.

Equity Valuation and Risks: For valuation methodology and risks associated with covered companies or price targets for covered companies, please see the most recent company-specific research report at http://www.jpmorganmarkets.com, contact the primary analyst or your J.P. Morgan representative, or email research.disclosure.inquiries@jpmorgan.com. For material information about the proprietary models used, please see the Summary of Financials in company-specific research reports and the Company Tearsheets, which are available to download on the company pages of our client website, http://www.jpmorganmarkets.com. This report also sets out within it the material underlying assumptions used.

# History of Investment Recommendations:

A history of J.P. Morgan investment recommendations disseminated during the preceding 12 months can be accessed on the Research & Commentary page of http://www.jpmorganmarkets.com where you can also search by analyst name, sector or financial instrument.

Analysts' Compensation:The research analysts responsible for the preparation of this report receive compensation based upon various factors including the quality and accuracy of research, client feedback, competitive factors, and overall firm revenues.

Registration of non-US Analysts: Unless otherwise noted, the non-US analysts listed on the front of this report are employees of non-US affiliates of J.P. Morgan Securities LLC, may not be registered as research analysts under FINRA rules, may not be associated persons of J.P.

Morgan Securities LLC, and may not be subject to FINRA Rule 2241 or 2242 restrictions on communications with covered companies, public appearances, and trading securities held by a research analyst account.

# Other Disclosures

J.P. Morgan is a marketing name for investment banking businesses of JPMorgan Chase & Co. and its subsidiaries and affiliates worldwide.

UK MIFID FICC research unbundling exemption: UK clients should refer to UK MIFID Research Unbundling exemption for details of J.   
Morgan’s implementation of the FICC research exemption and guidance on relevant FICC research categorisation.

All research material made available to clients are simultaneously available on our client website, J.P. Morgan Markets, unless specifically permitted by relevant laws. Not all research content is redistributed, e-mailed or made available to third-party aggregators. For all research material available on a particular stock, please contact your sales representative.

Any long form nomenclature for references to China; Hong Kong; Taiwan; and Macau within this research material are Mainland China; Hong Kong SAR (China); Taiwan (China); and Macau SAR (China).

J.P. Morgan Research may, from time to time, write on issuers or securities targeted by economic or financial sanctions imposed or administered by the governmental authorities of the U.S., EU, UK or other relevant jurisdictions (Sanctioned Securities). Nothing in this report is intended to be read or construed as encouraging, facilitating, promoting or otherwise approving investment or dealing in such Sanctioned Securities. Clients should be aware of their own legal and compliance obligations when making investment decisions.

Any digital or crypto assets discussed in this research report are subject to a rapidly changing regulatory landscape. For relevant regulatory advisories on crypto assets, including bitcoin and ether, please see https://www.jpmorgan.com/disclosures/cryptoasset-disclosure .

The author(s) of this research report may not be licensed to carry on regulated activities in your jurisdiction and, if not licensed, do not hold themselves out as being able to do so.

Exchange-Traded Funds (ETFs): J.P. Morgan Securities LLC (“JPMS”) acts as authorized participant for substantially all U.S.-listed ETFs. To the extent that any ETFs are mentioned in this report, JPMS may earn commissions and transaction-based compensation in connection with the distribution of those ETF shares and may earn fees for performing other trade-related services, such as securities lending to short sellers of the ETF shares. JPMS may also perform services for the ETFs themselves, including acting as a broker or dealer to the ETFs. In addition, affiliates of JPMS may perform services for the ETFs, including trust, custodial, administration, lending, index calculation and/or maintenance and other services.

Options and Futures related research: If the information contained herein regards options- or futures-related research, such information is available only to persons who have received the proper options or futures risk disclosure documents. Please contact your J.P. Morgan Representative or visit https://www.theocc.com/components/docs/riskstoc.pdf for a copy of the Option Clearing Corporation's Characteristics and Risks of Standardized Options or   
https://www.finra.org/sites/default/files/2020-08/Security_Futures_Risk_Disclosure_Statement_2020.pdf for a copy of the Security Futures Risk Disclosure Statement.

Changes to Interbank Offered Rates (IBORs) and other benchmark rates: Certain interest rate benchmarks are, or may in the future become, subject to ongoing international, national and other regulatory guidance, reform and proposals for reform. For more information, please consult: https://www.jpmorgan.com/global/disclosures/interbank_offered_rates

Private Bank Clients: Where you are receiving research as a client of the private banking businesses offered by JPMorgan Chase & Co. and its subsidiaries (“J.P. Morgan Private Bank”), research is provided to you by J.P. Morgan Private Bank and not by any other division of J.P. Morgan, including, but not limited to, the J.P. Morgan Corporate and Investment Bank and its Global Research division.

Legal entity responsible for the production and distribution of research: The legal entity identified below the name of the Reg AC Research Analyst who authored this material is the legal entity responsible for the production of this research. Where multiple Reg AC Research Analysts authored this material with different legal entities identified below their names, these legal entities are jointly responsible for the production of this research. Where more than one legal entity is listed under an analyst’s name, the first legal entity is responsible for the production unless stated otherwise. Research Analysts from various J.P. Morgan affiliates may have contributed to the production of this material but may not be licensed to carry out regulated activities in your jurisdiction (and do not hold themselves out as being able to do so). Unless otherwise stated below in the legal entity disclosures, this material has been distributed by the legal entity responsible for production, or where more than one legal entity is listed under the analyst’s name, the first legal entity will be responsible for distribution. If you have any queries, please contact the relevant Research Analyst in your jurisdiction or the entity in your jurisdiction that has distributed this research material.

# Legal Entities Disclosures and Country-/Region-Specific Disclosures:

Argentina: JPMorgan Chase Bank N.A Sucursal Buenos Aires is regulated by Banco Central de la República Argentina (“BCRA”- Central Bank of Argentina) and Comisión Nacional de Valores (“CNV”- Argentinian Securities Commission - ALYC y AN Integral $\mathrm { N } ^ { \circ } 5 1$ ).

Australia: J.P. Morgan Securities Australia Limited (“JPMSAL”) (ABN 61 003 245 234/AFS Licence No: 238066) is regulated by the Australian Securities and Investments Commission and is a Market Participant of ASX Limited, a Clearing and Settlement Participant of ASX

Clear Pty Limited and a Clearing Participant of ASX Clear (Futures) Pty Limited. This material is issued and distributed in Australia by or on behalf of JPMSAL only to "wholesale clients" (as defined in section 761G of the Corporations Act 2001). A list of all financial products covered can be found by visiting https://www.jpmm.com/research/disclosures. J.P. Morgan seeks to cover companies of relevance to the domestic and international investor base across all Global Industry Classification Standard (GICS) sectors, as well as across a range of market capitalisation sizes. If applicable, in the course of conducting public side due diligence on the subject company(ies), the Research Analyst team may at times perform such diligence through corporate engagements such as site visits, discussions with company representatives, management presentations, etc. Research issued by JPMSAL has been prepared in accordance with J.P. Morgan Australia’s Research Independence Policy which can be found at the following link: J.P. Morgan Australia - Research Independence Policy.

Brazil: Banco J.P. Morgan S.A. is regulated by the Comissao de Valores Mobiliarios (CVM) and by the Central Bank of Brazil. Ombudsman J.P. Morgan: 0800-7700847 / 0800-7700810 (For Hearing Impaired) / ouvidoria.jp.morgan@jpmchase.com.

Canada: J.P. Morgan Securities Canada Inc. is a registered investment dealer, regulated by the Canadian Investment Regulatory Organization and the Ontario Securities Commission and is the participating member on Canadian exchanges. This material is distributed in Canada by or on behalf of J.P.Morgan Securities Canada Inc.

Chile: Inversiones J.P. Morgan Limitada is an unregulated entity incorporated in Chile.

China: J.P. Morgan Securities (China) Company Limited has been approved by CSRC to conduct the securities investment consultancy business.

Colombia: Banco J.P. Morgan Colombia S.A. is supervised by the Superintendencia Financiera de Colombia (SFC).

Dubai International Financial Centre (DIFC): JPMorgan Chase Bank, N.A., Dubai Branch is regulated by the Dubai Financial Services Authority (DFSA) and its registered address is Dubai International Financial Centre - The Gate, West Wing, Level 3 and 9 PO Box 506551, Dubai, UAE. This material has been distributed by JP Morgan Chase Bank, N.A., Dubai Branch to persons regarded as professional clients or market counterparties as defined under the DFSA rules.

European Economic Area (EEA): Unless specified to the contrary, research is distributed in the EEA by J.P. Morgan SE (“JPM SE”), which is authorised as a credit institution by the Federal Financial Supervisory Authority (Bundesanstalt für Finanzdienstleistungsaufsicht, BaFin) and jointly supervised by the BaFin, the German Central Bank (Deutsche Bundesbank) and the European Central Bank (ECB). JPM SE is a company headquartered in Frankfurt with registered address at TaunusTurm, Taunustor 1, Frankfurt am Main, 60310, Germany. The material has been distributed in the EEA to persons regarded as professional investors (or equivalent) pursuant to Art. 4 para. 1 no. 10 and Annex II of MiFID II and its respective implementation in their home jurisdictions (“EEA professional investors”). This material must not be acted on or relied on by persons who are not EEA professional investors. Any investment or investment activity to which this material relates is only available to EEA relevant persons and will be engaged in only with EEA relevant persons.

Hong Kong: J.P. Morgan Securities (Asia Pacific) Limited (CE number AAJ321) is regulated by the Hong Kong Monetary Authority and the Securities and Futures Commission in Hong Kong, and J.P. Morgan Broking (Hong Kong) Limited (CE number AAB027) is regulated by the Securities and Futures Commission in Hong Kong. JP Morgan Chase Bank, N.A., Hong Kong Branch (CE Number AAL996) is regulated by the Hong Kong Monetary Authority and the Securities and Futures Commission, is organized under the laws of the United States with limited liability. Where the distribution of this material is a regulated activity in Hong Kong, the material is distributed in Hong Kong by or through J.P. Morgan Securities (Asia Pacific) Limited and/or J.P. Morgan Broking (Hong Kong) Limited.

India: J.P. Morgan India Private Limited (Corporate Identity Number - U67120MH1992FTC068724), having its registered office at J.P. Morgan Tower, Off. C.S.T. Road, Kalina, Santacruz - East, Mumbai – 400098, is registered with the Securities and Exchange Board of India (SEBI) as a ‘Research Analyst’ having registration number INH000001873. J.P. Morgan India Private Limited is also registered with SEBI as a member of the National Stock Exchange of India Limited and the Bombay Stock Exchange Limited (SEBI Registration Number – INZ000239730) and as a Merchant Banker (SEBI Registration Number - MB/INM000002970). Telephone: 91-22-6157 3000, Facsimile: 91-22-6157 3990 and Website: http://www.jpmipl.com . JPMorgan Chase Bank, N.A. - Mumbai Branch is licensed by the Reserve Bank of India (RBI) (Licence No. 53/ Licence No. BY.4/94; SEBI - IN/CUS/014/ CDSL : IN-DP-CDSL-444-2008/ IN-DP-NSDL-285-2008/ INBI00000984/ INE231311239) as a Scheduled Commercial Bank in India, which is its primary license allowing it to carry on Banking business in India and other activities, which a Bank branch in India are permitted to undertake. For non-local research material, this material is not distributed in India by J.P. Morgan India Private Limited. Compliance Officer: Spurthi Gadamsetty; spurthi.gadamsetty@jpmchase.com; +912261573225. Grievance Officer: Ramprasadh K, jpmipl.research.feedback@jpmorgan.com; +912261573000. Registration granted by SEBI and certification from NISM in no way guarantee performance of the intermediary or provide any assurance of returns to investors.

Indonesia: PT J.P. Morgan Sekuritas Indonesia is a member of the Indonesia Stock Exchange and is registered and supervised by the Otoritas Jasa Keuangan (OJK).

Korea: J.P. Morgan Securities (Far East) Limited, Seoul Branch, is a member of the Korea Exchange (KRX). JPMorgan Chase Bank, N.A., Seoul Branch, is licensed as a branch office of foreign bank (JPMorgan Chase Bank, N.A.) in Korea. Both entities are regulated by the Financial Services Commission (FSC) and the Financial Supervisory Service (FSS). For non-macro research material, the material is distributed in Korea by or through J.P. Morgan Securities (Far East) Limited, Seoul Branch.

Japan: JPMorgan Securities Japan Co., Ltd. and JPMorgan Chase Bank, N.A., Tokyo Branch are regulated by the Financial Services Agency in Japan.

Dobromir Tzotchev, PhD AC (44-20) 7134-5331 dobromir.tzotchev@jpmorgan.com

Global Markets Strategy Equity Volatility Strategy 05 June 2025

Yangyang Hou AC (44-20) 3493-1012 yangyang.hou@jpmorgan.com J.P. Morgan Securities plc Emma Wu AC (1-212) 834-2174 emma.wu@jpmorgan.com

Tony SK Lee (852) 2800-8857 tony.sk.lee@jpmorgan.com

Malaysia: This material is issued and distributed in Malaysia by JPMorgan Securities (Malaysia) Sdn Bhd (18146-X), which is a Participating Organization of Bursa Malaysia Berhad and holds a Capital Markets Services License issued by the Securities Commission in Malaysia.

Mexico: J.P. Morgan Casa de Bolsa, S.A. de C.V. and J.P. Morgan Grupo Financiero are members of the Mexican Stock Exchange and are authorized to act as a broker dealer by the National Banking and Securities Exchange Commission.

New Zealand: This material is issued and distributed by JPMSAL in New Zealand only to "wholesale clients" (as defined in the Financial Markets Conduct Act 2013). JPMSAL is registered as a Financial Service Provider under the Financial Service providers (Registration and Dispute Resolution) Act of 2008.

Philippines: J.P. Morgan Securities Philippines Inc. is a Trading Participant of the Philippine Stock Exchange and a member of the Securities Clearing Corporation of the Philippines and the Securities Investor Protection Fund. It is regulated by the Securities and Exchange Commission.

Singapore: This material is issued and distributed in Singapore by or through J.P. Morgan Securities Singapore Private Limited (JPMSS) [MDDI (P) 068/08/2024 and Co. Reg. No.: 199405335R], which is a member of the Singapore Exchange Securities Trading Limited, and/or JPMorgan Chase Bank, N.A., Singapore branch (JPMCB Singapore), both of which are regulated by the Monetary Authority of Singapore. This material is issued and distributed in Singapore only to accredited investors, expert investors and institutional investors, as defined in Section 4A of the Securities and Futures Act, Cap. 289 (SFA). This material is not intended to be issued or distributed to any retail investors or any other investors that do not fall into the classes of “accredited investors,” “expert investors” or “institutional investors,” as defined under Section 4A of the SFA. Recipients of this material in Singapore are to contact JPMSS or JPMCB Singapore in respect of any matters arising from, or in connection with, the material.

South Africa: J.P. Morgan Equities South Africa Proprietary Limited and JPMorgan Chase Bank, N.A., Johannesburg Branch are members of the Johannesburg Securities Exchange and are regulated by the Financial Services Conduct Authority (FSCA).

Taiwan: J.P. Morgan Securities (Taiwan) Limited is a participant of the Taiwan Stock Exchange (company-type) and regulated by the Taiwan Securities and Futures Bureau. Material relating to equity securities is issued and distributed in Taiwan by J.P. Morgan Securities (Taiwan) Limited, subject to the license scope and the applicable laws and the regulations in Taiwan. To the extent that J.P. Morgan Securities (Taiwan) Limited produces research materials on securities not listed on the Taiwan Stock Exchange or Taipei Exchange (“Non-Taiwan Listed Securities”), these materials shall not constitute securities recommendations for the purpose of applicable Taiwan regulations, and, for the avoidance of doubt, J.P. Morgan Securities (Taiwan) Limited does not act as broker for Non-Taiwan Listed Securities. According to Paragraph 2, Article 7-1 of Operational Regulations Governing Securities Firms Recommending Trades in Securities to Customers (as amended or supplemented) and/or other applicable laws or regulations, please note that the recipient of this material is not permitted to engage in any activities in connection with the material that may give rise to conflicts of interests, unless otherwise disclosed in the “Important Disclosures” in this material.

Thailand: This material is issued and distributed in Thailand by JPMorgan Securities (Thailand) Ltd., which is a member of the Stock Exchange of Thailand and is regulated by the Ministry of Finance and the Securities and Exchange Commission, and its registered address is 3rd Floor, 20 North Sathorn Road, Silom, Bangrak, Bangkok 10500.

UK: Research is produced in the UK by J.P. Morgan Securities plc (“JPMS plc”) which is a member of the London Stock Exchange and is authorised by the Prudential Regulation Authority and regulated by the Financial Conduct Authority and the Prudential Regulation Authority or J.P. Morgan Markets Limited (“JPMML Ltd”) which is authorised and regulated by the Financial Conduct Authority. Unless specified to the contrary, this material is distributed in the UK by JPMS plc and is directed in the UK only to: (a) persons having professional experience in matters relating to investments falling within article 19(5) of the Financial Services and Markets Act 2000 (Financial Promotion) (Order) 2005 (“the FPO”); (b) persons outlined in article 49 of the FPO (high net worth companies, unincorporated associations or partnerships, the trustees of high value trusts, etc.); or (c) any persons to whom this communication may otherwise lawfully be made; all such persons being referred to as "UK relevant persons". This material must not be acted on or relied on by persons who are not UK relevant persons. Any investment or investment activity to which this material relates is only available to UK relevant persons and will be engaged in only with UK relevant persons. A description of J.P. Morgan EMEA’s policy for prevention and avoidance of conflicts of interest related to the production of Research can be found at the following link: J.P. Morgan EMEA - Research Independence Policy.

U.S.: J.P. Morgan Securities LLC (“JPMS”) is a member of the NYSE, FINRA, SIPC, and the NFA. JPMorgan Chase Bank, N.A. is a member of the FDIC. Material published by non-U.S. affiliates is distributed in the U.S. by JPMS who accepts responsibility for its content.

General: Additional information is available upon request. The information in this material has been obtained from sources believed to be reliable. While all reasonable care has been taken to ensure that the facts stated in this material are accurate and that the forecasts, opinions and expectations contained herein are fair and reasonable, JPMorgan Chase & Co. or its affiliates and/or subsidiaries (collectively J.P. Morgan) make no representations or warranties whatsoever to the completeness or accuracy of the material provided, except with respect to any disclosures relative to J.P. Morgan and the Research Analyst's involvement with the issuer that is the subject of the material. Accordingly, no reliance should be placed on the accuracy, fairness or completeness of the information contained in this material. There may be certain discrepancies with data and/or limited content in this material as a result of calculations, adjustments, translations to different languages, and/or local regulatory restrictions, as applicable. These discrepancies should not impact the overall investment analysis, views and/or recommendations of the subject company(ies) that may be discussed in the material. Artificial intelligence tools may have been used in the preparation of this material, including assisting in data analysis, pattern recognition, and content drafting for research material. J.P. Morgan accepts no liability whatsoever for any loss arising from any use of this material or its contents, and neither J.P. Morgan nor any of its respective directors, officers or employees, shall be in any way responsible for the contents hereof, apart from the liabilities and responsibilities that may be imposed on them by the relevant regulatory authority in the jurisdiction in question, or the regulatory regime thereunder. Opinions, forecasts or projections contained in this material represent J.P. Morgan's current opinions or judgment as of the date of the material only and are therefore subject to change without notice. Periodic updates may be provided on companies/industries based on company-specific developments or announcements, market conditions or any other publicly available information. There can be no assurance that future results or events will be consistent with any such opinions, forecasts or projections, which represent only one possible outcome. Furthermore, such opinions, forecasts or projections are subject to certain risks, uncertainties and assumptions that have not been verified, and future actual results or events could differ materially. The value of, or income from, any investments referred to in this material may fluctuate and/or be affected by changes in exchange rates. All pricing is indicative as of the close of market for the securities discussed, unless otherwise stated. Past performance is not indicative of future results. Accordingly, investors may receive back less than originally invested. This material is not intended as an offer or solicitation for the purchase or sale of any financial instrument. The opinions and recommendations herein do not take into account individual client circumstances, objectives, or needs and are not intended as recommendations of particular securities, financial instruments or strategies to particular clients. This material may include views on structured securities, options, futures and other derivatives. These are complex instruments, may involve a high degree of risk and may be appropriate investments only for sophisticated investors who are capable of understanding and assuming the risks involved. The recipients of this material must make their own independent decisions regarding any securities or financial instruments mentioned herein and should seek advice from such independent financial, legal, tax or other adviser as they deem necessary. J.P. Morgan may trade as a principal on the basis of the Research Analysts’ views and research, and it may also engage in transactions for its own account or for its clients’ accounts in a manner inconsistent with the views taken in this material, and J.P. Morgan is under no obligation to ensure that such other communication is brought to the attention of any recipient of this material. Others within J.P. Morgan, including Strategists, Sales staff and other Research Analysts, may take views that are inconsistent with those taken in this material. Employees of J.P. Morgan not involved in the preparation of this material may have investments in the securities (or derivatives of such securities) mentioned in this material and may trade them in ways different from those discussed in this material. This material is not an advertisement for or marketing of any issuer, its products or services, or its securities in any jurisdiction.

Confidentiality and Security Notice: This transmission may contain information that is privileged, confidential, legally privileged, and/or exempt from disclosure under applicable law. If you are not the intended recipient, you are hereby notified that any disclosure, copying, distribution, or use of the information contained herein (including any reliance thereon) is STRICTLY PROHIBITED. Although this transmission and any attachments are believed to be free of any virus or other defect that might affect any computer system into which it is received and opened, it is the responsibility of the recipient to ensure that it is virus free and no responsibility is accepted by JPMorgan Chase & Co., its subsidiaries and affiliates, as applicable, for any loss or damage arising in any way from its use. If you received this transmission in error, please immediately contact the sender and destroy the material in its entirety, whether in electronic or hard copy format. This message is subject to electronic monitoring: https://www.jpmorgan.com/disclosures/email

MSCI: Certain information herein (“Information”) is reproduced by permission of MSCI Inc., its affiliates and information providers (“MSCI”) $\textcircled { \mathrm { C } } 2 0 2 5$ . No reproduction or dissemination of the Information is permitted without an appropriate license. MSCI MAKES NO EXPRESS OR IMPLIED WARRANTIES (INCLUDING MERCHANTABILITY OR FITNESS) AS TO THE INFORMATION AND DISCLAIMS ALL LIABILITY TO THE EXTENT PERMITTED BY LAW. No Information constitutes investment advice, except for any applicable Information from MSCI ESG Research. Subject also to msci.com/disclaimer

Sustainalytics: Certain information, data, analyses and opinions contained herein are reproduced by permission of Sustainalytics and: (1) includes the proprietary information of Sustainalytics; (2) may not be copied or redistributed except as specifically authorized; (3) do not constitute investment advice nor an endorsement of any product or project; (4) are provided solely for informational purposes; and (5) are not warranted to be complete, accurate or timely. Sustainalytics is not responsible for any trading decisions, damages or other losses related to it or its use. The use of the data is subject to conditions available at https://www.sustainalytics.com/legal-disclaimers . $\textcircled { \mathrm { C } } 2 0 2 5$ Sustainalytics. All Rights Reserved.

"Other Disclosures" last revised May 24, 2025.

Copyright 2025 JPMorgan Chase & Co. All rights reserved. This material or any portion hereof may not be reprinted, sold or redistributed without the written consent of J.P. Morgan. It is strictly prohibited to use or share without prior written consent from J.P. Morgan any research material received from J.P. Morgan or an authorized third-party (“J.P. Morgan Data”) in any third-party artificial intelligence (“AI”) systems or models when such J.P. Morgan Data is accessible by a third-party. It is permissible to use J.P. Morgan Data for internal business purposes only in an AI system or model that protects the confidentiality of J.P. Morgan Data so as to prevent any and all access to or use of such J.P. Morgan Data by any third-party.