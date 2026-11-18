import pandas as pd, numpy as np
pd.set_option('display.width',250); pd.set_option('display.max_columns',60); pd.set_option('display.max_rows',200)
D='d:/IPl/Data Pack/'
fs=['ball_by_ball','matches','competitions','playing_eleven','competition_team_player_mapping','teams']
T={f:pd.read_csv(D+f+'.csv',low_memory=False) for f in fs}
for f,d in T.items():
    print('\n=====',f,d.shape,'dups:',d.duplicated().sum())
    print(pd.DataFrame({'dtype':d.dtypes.astype(str),'nulls':d.isna().sum(),'nunique':d.nunique(),'sample':d.iloc[0]}))
b,m,c=T['ball_by_ball'],T['matches'],T['competitions']
for col in ['extras_type','dismissal_type','pace_or_spin','batting_type','bowling_type']: print('\n',col,b[col].value_counts(dropna=False).to_dict())
print('innings',b.innings.value_counts().to_dict())
print('runs',b.runs.value_counts().to_dict())
for col in ['is_four','is_six','is_wicket']: print(col,b[col].value_counts(dropna=False).to_dict())
for col in ['stage','knock_out','result','toss_opted','venue_country']: print('\n',col,m[col].value_counts(dropna=False).to_dict())
print(m.match_date.min(),m.match_date.max())
print(c)
print('first_inn_revised_overs',m.first_inn_revised_overs.value_counts(dropna=False).to_dict())
print('second_inn_revised_overs',m.second_inn_revised_overs.value_counts(dropna=False).to_dict())
print('revised_target nonnull',m.revised_target.notna().sum())
print('win_team null',m.win_team_id.isna().sum())
mm=m.merge(c,on='comp_id',how='left'); mm['year']=pd.to_datetime(mm.match_date,errors='coerce').dt.year
print(mm.groupby(['comp_name','season']).size())
print(pd.crosstab(mm.comp_name,mm.year))
print('matches in bbb',b.match_id.nunique(),'in matches',m.match_id.nunique(),'bbb not in matches',len(set(b.match_id)-set(m.match_id)))
print(b.groupby('match_id').innings.nunique().value_counts())
print(b.overid.describe(), b.overid.max())
