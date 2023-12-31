import numpy as np
import pandas as pd
import os
import configparser
from mysystem.factor_test import factor_constructor
import math
import matplotlib.pyplot as plt
from scipy.stats import t

# 对因子进行一站式测试
def wrapup_test(pctdf,data,agg_func,require_returns = False, require_submit = False, cta = False, detailed = False,\
    sell_threshold=None,buy_threshold=None,startdate=None,enddate=None):
    
    factor = factor_constructor.get_price_factor(data,agg_func,startdate,enddate)
    
    if not cta:
        results = single_factor_backtest(pctdf,factor,num_bins=5)
        show(results,detailed)
        
    else:
        results = single_factor_cta_backtest(pctdf,factor,sell_threshold,buy_threshold)
        show(results,detailed,cta=True)
    
    if require_submit:
        submit(factor,results,'Unnamed','研究员使用了默认测试提交，因此未给出说明',cta)
        
    if require_returns:
        return factor, results

# 对CTA策略进行回测
def single_factor_cta_backtest(pctdf,factor,sell_threshold,buy_threshold):
    
    factor = factor.shift(1)
    weights = ((factor > buy_threshold).astype('int') - (factor < sell_threshold).astype('int'))
    ls_ret = (weights * pctdf).sum(axis=1) / abs(weights).sum(axis=1)
    
    return ls_ret

# 对截面因子进行分组回测
def single_factor_backtest(pctdf,factor,num_bins=10):
    
    print('正在计算分组收益')
    # 计算分组收益
    factor = factor.shift(1)
    stock_num = (factor.shape[1] - factor.isna().sum(axis=1))/num_bins
    factor_rank = factor.rank(na_option='keep',axis=1)
    bin = num_bins - factor_rank.divide(stock_num,axis=0).replace([np.inf, -np.inf], np.nan)
    bin = bin.applymap(lambda x: int(x) if not pd.isna(x) else x)
    for j in range(num_bins):
        pctdf['group '+str(j)] = np.nan
    for i in pctdf.index:
        for j in range(num_bins):
            pctdf['group '+str(j)][i] = pctdf.loc[i].iloc[:-num_bins][bin.loc[i]==j].mean()
    ans = pctdf.iloc[:,-num_bins:]
    ans = ans.dropna()
    for j in range(num_bins):
        del pctdf['group '+str(j)]
    
    print('正在计算IC')
    # 计算IC/rankIC
    rankic = pd.Series([pctdf.iloc[i].corr(factor_rank.iloc[i]) for i in range(len(pctdf))])
    rankic.index = pctdf.index
    ans['rankIC'] = rankic
    
    ic = pd.Series([pctdf.iloc[i].corr(factor.iloc[i]) for i in range(len(pctdf))])
    ic.index = pctdf.index
    ans['IC'] = ic
    
    return ans

# 展示截面因子回测结果
def show(results, detailed = False, cta = False):
    
    if not cta:
        returns = results.iloc[:,:-2]
        IC = results.iloc[:,-2:]
        ls_ret = (returns.iloc[:,0] - returns.iloc[:,-1])
    else:
        ls_ret = results
        
    print('多空组合:')
    mean,sd,sr,dd = get_stats(ls_ret.dropna(),show=True)
    
    if not cta:
        print('多头超额:')
        mean,sd,sr,dd = get_stats(returns.dropna().iloc[:,0] - returns.dropna().mean(axis=1),show=True)
        print('纯多头：')
        mean,sd,sr,dd = get_stats(returns.dropna().iloc[:,0],show=True)
        
        tstat = IC['IC'].mean() * np.sqrt(IC['IC'].shape[0]) / IC['IC'].std()
        pval = t.sf(abs(tstat), IC['IC'].shape[0])
        
        print('IC相关数据：')
        
        df = pd.DataFrame(data=np.zeros((1,6)),\
            columns=['RankIC均值','RankIC标准差','IC均值','IC标准差','T统计量','显著性水平(p-value)'],index=['数值'])
        df.iloc[0] = [IC['rankIC'].mean(),IC['rankIC'].std(),IC['IC'].mean(),IC['IC'].std(),tstat,pval]
        display(df)
        
        if detailed:
            plot(returns)        
    
    else:
        if detailed:
            plot(ls_ret,cta=True)
            
    if detailed:
        print('多空组合逐月收益：')
        df = pd.DataFrame(ls_ret)
        monthly_means = df.resample('M').mean().reset_index()
        monthly_means['year'] = monthly_means['date'].apply(lambda x:x.year)
        monthly_means['month'] = monthly_means['date'].apply(lambda x:x.month)
        yearly_means = monthly_means.groupby(['month','year']).agg({0:'sum'}).unstack()[0].T

        styled_df = yearly_means.style.bar(color=['green', 'red'], align='zero')
        display(styled_df)

# 提交因子
def submit(factor,results,name,comment,cta=False):
    
    username = os.getlogin()
    
    # 读取判断标准阈值
    config = configparser.ConfigParser()
    config.read('./mysystem/config.ini')
    corr_barrier = float(config.get('settings', 'corr'))
    sr_bar = float(config.get('settings', 'sharpe'))
    
    if not cta:
        returns = results.iloc[:,:-2]
        ls_ret = returns.iloc[:,0] - returns.iloc[:,-1]
        mean,sd,sr,dd = get_stats((returns.iloc[:,0] - returns.iloc[:,-1]).dropna())
    else:
        mean,sd,sr,dd = get_stats((results).dropna())
        ls_ret = results
        
    corr = 0
    print('正在检验相关性和收益情况')
    corr = get_corr(ls_ret)
    
    # 判断是否符合入库条件
    if corr>corr_barrier:
        print('相关性过高！拒绝入库')
    elif sr<sr_bar:
        print('收益过低！拒绝入库')
        
    # 入库
    else:
        os.makedirs('./mysystem/factors/'+str(name))
        factor.reset_index().to_feather('./mysystem/factors/'+str(name)+'/value.feather')
            
        ls_ret.to_csv('./mysystem/factors/'+str(name)+'/lsreturn.csv')
        file = open('./mysystem/factors/'+str(name)+'/comments.txt','w')
        file.write(comment+'\nContributer: '+ username )
        file.close()
        print('Submit Success')
   
################################# 辅助函数 #################################        

def plot(results,cta = False):
    
    clean_results = results.dropna()
    
    if not cta:
        (clean_results+1).cumprod().plot(legend=True,title='分组收益',figsize=(12,4))
        pd.DataFrame((clean_results.iloc[:,0] - clean_results.iloc[:,-1]+1).cumprod())\
            .plot(legend=False,title='多空收益',figsize=(12,4))
    else:
        pd.DataFrame((clean_results+1).cumprod()).plot(legend=False,title='多空收益',figsize=(12,4))

def get_stats(x,show=False,ret=True):
    
    mean = x.mean()*252
    sd = x.std()*math.sqrt(252)
    sr = mean/sd
    tmp = (1+x).cumprod()
    dd = ((tmp.cummax()-tmp)/tmp.cummax()).max()
    if show:
        df = pd.DataFrame(data=np.zeros((1,4)),columns=['年化收益(%)','年化波动(%)','夏普率','回撤(%)'],index=['数值'])
        df.iloc[0] = [mean*100,sd*100,sr,dd*100]
        display(df)
    if ret:
        return mean,sd,sr,dd

def get_corr(lsret):
    
    candidates = os.listdir('./mysystem/factors/')
    corr = 0
    for i in candidates:
        old_ret = pd.read_csv('./mysystem/factors/'+i+'/lsreturn.csv').rename(columns={'0':'old'})
        old_ret['date'] = pd.to_datetime(old_ret['date'])
        new_ret = pd.DataFrame(lsret).reset_index().rename(columns={0:'new'})
        tmp = old_ret.merge(new_ret).dropna()[['old','new']].corr().iloc[1,0]
        corr = max(abs(tmp),corr)
    print('最大相关性:{:.3f}'.format(corr))
    return corr