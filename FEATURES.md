# Statistics Features - User Guide

## What's New? 🎉

We've improved how statistics are calculated and displayed throughout the NFL Pick'em app! Here's what changed:

### 1. Missed Games Now Count! ⚠️

**What changed:**
- Previously, if you didn't make a pick for a game, it didn't affect your accuracy
- Now, missed games reduce your accuracy percentage (like a loss)
- However, missed games DON'T count as losses in your win/loss record
- They also don't affect your tiebreaker points

**Why this matters:**
- Prevents "cherry-picking" only easy games to boost accuracy
- Encourages consistent participation
- More accurately reflects your overall performance

**Example:**
- **Before**: 5 wins, 2 losses, 3 missed games = 71% accuracy (5/7)
- **Now**: 5 wins, 2 losses, 3 missed games = 50% accuracy (5/10)

### 2. Enhanced Pick'em Screen Statistics 📊

**Where to find it:** Click "Picks" in the navigation menu

**What you'll see:**
A prominent statistics dashboard showing your performance in the selected group:

- **Wins** 🟢 - Your correct picks
- **Losses** 🔴 - Your incorrect picks  
- **Missed** 🟠 - Games you didn't pick
- **Accuracy** - Win percentage (includes missed games)
- **Tiebreaker** - Your total tiebreaker points
- **Streak** - Current winning or losing streak

**Color-coded accuracy:**
- Green: 60% or higher (Great job!)
- Orange: 40-60% (Room for improvement)
- Red: Below 40% (Keep trying!)

### 3. Improved User Profile 👤

**Where to find it:** Click your username → "Profile"

**New sections:**

#### All-Time Career Statistics
Shows your overall performance across ALL seasons and groups:
- Career wins, losses, and missed games
- Overall accuracy percentage
- Total tiebreaker points earned
- Total picks made and groups joined

#### Current Season Performance
Displays stats for just the current season:
- Season wins, losses, missed games
- Season accuracy and tiebreaker points
- Current winning/losing streak

**Pro tip:** This is where you see your TRUE overall performance, not just one group!

### 4. Global Leaderboard 🏆

**Where to find it:** Click "Leaderboard" in the navigation menu

**New filter system:**

#### All-Time View (Default)
- Shows career statistics for all players
- Aggregates performance across all seasons
- Perfect for seeing who the all-time champions are
- Sorted by total wins, then tiebreaker points

#### Season View
- Filter by specific season (current or past)
- Shows performance for that season only
- Includes streak information
- Great for season-specific competitions

**How to use filters:**
1. Select "All-Time Statistics" or "By Season" from the dropdown
2. If selecting "By Season", choose the season from the second dropdown
3. Click "Apply Filters"

**What you'll see:**
- **Rank** - Your position (top 3 get special badges! 🥇🥈🥉)
- **Wins** - Correct picks
- **Losses** - Incorrect picks
- **Missed** - Games not picked
- **Accuracy** - Win percentage
- **Tiebreaker** - Total points
- **Streak** - Current streak (season view only)

## Understanding Your Stats

### Group-Specific vs Global Statistics

**Group-Specific Stats** (shown on Pick'em screen):
- If you have `picks_are_global = False`:
  - Each group shows ONLY picks made for that group
  - Your stats differ between groups
- If you have `picks_are_global = True`:
  - Same picks apply to all groups
  - Stats are consistent across all groups

**Global Stats** (shown on Profile and Leaderboard):
- Profile: ALL your picks across ALL groups and seasons
- Leaderboard: Can be filtered by all-time or specific season

### Accuracy Calculation

**Formula:**
```
Accuracy = Wins / (Wins + Losses + Missed Games) × 100
```

**What counts:**
- ✅ **Wins** increase accuracy
- ❌ **Losses** decrease accuracy  
- ⚠️ **Missed games** decrease accuracy (NEW!)

**What doesn't count:**
- Pending picks (games not yet completed)
- Picks for games that were cancelled

### Tiebreaker Points

- Only awarded for completed picks (win or lose)
- Winning pick: Margin of victory (positive points)
- Losing pick: Negative margin (negative points)
- Missed games: 0 points (no pick made)

## Tips for Success 🎯

1. **Make picks for every game** - Avoid missed games to maintain accuracy
2. **Check the Pick'em screen regularly** - Stats update in real-time
3. **View your profile** - Track long-term improvement
4. **Check the global leaderboard** - See how you rank against all players
5. **Monitor your streak** - Try to build winning streaks for momentum!

## Frequently Asked Questions

**Q: Why did my accuracy go down?**
A: Missed games now count against your accuracy. Make sure to pick for all games!

**Q: Do missed games count as losses in my record?**
A: No! Missed games reduce accuracy but don't add to your loss count.

**Q: Where can I see my stats for a specific group?**
A: On the Pick'em screen, select the group from the dropdown. Stats shown are for that group only.

**Q: How do I see my overall career stats?**
A: Go to your Profile page. The "All-Time Statistics" section shows your career totals.

**Q: Can I compare my stats to other players?**
A: Yes! Visit the Leaderboard page and use the filters to see rankings.

**Q: What's the difference between "All-Time" and "Season" on the leaderboard?**
A: All-Time shows career totals across all seasons. Season shows stats for one specific season.

## Need Help?

If you have questions or notice any issues with the statistics, please contact the administrator or report an issue through the app's feedback system.

Happy picking! 🏈
