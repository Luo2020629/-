import tushare as ts
import pandas as pd
from datetime import datetime, timedelta
import time
import os

# 设置token
ts.set_token('5d40bdab9e44cb18a8eaff2961932bebd34ff3d9f0a97abc84a2acbf')
pro = ts.pro_api()

class FullStockScreener:
    def __init__(self):
        self.stock_data = None
        self.all_stocks = None
    
    def get_all_stock_list(self):
        """
        获取沪深所有正常上市的股票列表
        """
        try:
            # 获取基础信息数据，包括股票代码、名称、上市状态等
            df = pro.stock_basic(exchange='', list_status='L', 
                                fields='ts_code,symbol,name,area,industry,list_date,market')
            self.all_stocks = df['ts_code'].tolist()
            print(f"获取到 {len(self.all_stocks)} 只正常上市的股票")
            return self.all_stocks
        except Exception as e:
            print(f"获取股票列表失败: {e}")
            return []
    
    def get_all_stocks_daily_data(self, start_date, end_date, batch_size=50):
        """
        分批获取所有股票的日线数据
        batch_size: 每批获取的股票数量，避免请求过于频繁
        """
        if self.all_stocks is None:
            self.get_all_stock_list()
        
        if not self.all_stocks:
            print("没有获取到股票列表")
            return pd.DataFrame()
        
        all_data = []
        total_stocks = len(self.all_stocks)
        
        print(f"开始获取 {total_stocks} 只股票的日线数据...")
        print(f"时间范围: {start_date} 到 {end_date}")
        
        for i in range(0, total_stocks, batch_size):
            batch = self.all_stocks[i:i + batch_size]
            batch_num = i // batch_size + 1
            total_batches = (total_stocks + batch_size - 1) // batch_size
            
            print(f"正在获取第 {batch_num}/{total_batches} 批数据 ({len(batch)} 只股票)...")
            
            batch_data = []
            for j, stock_code in enumerate(batch):
                try:
                    # 添加延时避免频繁请求
                    if j > 0 and j % 10 == 0:
                        time.sleep(1)  # 每10只股票暂停1秒
                    
                    df = pro.daily(ts_code=stock_code, 
                                  start_date=start_date, 
                                  end_date=end_date)
                    
                    if not df.empty:
                        batch_data.append(df)
                        print(f"  ✓ {stock_code} - {len(df)} 条记录")
                    else:
                        print(f"  ⚠ {stock_code} 无数据")
                        
                except Exception as e:
                    print(f"  ✗ {stock_code} 获取失败: {e}")
                    continue
            
            if batch_data:
                # 合并这批数据
                batch_df = pd.concat(batch_data, ignore_index=True)
                all_data.append(batch_df)
            
            # 批次间延时
            if i + batch_size < total_stocks:
                print(f"等待3秒后继续下一批...")
                time.sleep(3)
        
        if all_data:
            self.stock_data = pd.concat(all_data, ignore_index=True)
            # 转换日期格式并排序
            self.stock_data['trade_date'] = pd.to_datetime(self.stock_data['trade_date'])
            self.stock_data = self.stock_data.sort_values(['ts_code', 'trade_date'])
            
            print(f"\n数据获取完成！共 {len(self.stock_data)} 条记录")
            print(f"时间范围: {self.stock_data['trade_date'].min()} 到 {self.stock_data['trade_date'].max()}")
            print(f"股票数量: {self.stock_data['ts_code'].nunique()} 只")
            
            return self.stock_data
        else:
            print("没有获取到任何数据")
            return pd.DataFrame()
    
    def get_single_date_data(self, target_date):
        """
        获取特定日期的全市场数据（更高效的方法）
        """
        try:
            print(f"正在获取 {target_date} 的全市场日线数据...")
            
            # 使用日线行情接口直接获取某一天的所有股票数据
            df = pro.daily(trade_date=target_date)
            
            if not df.empty:
                df['trade_date'] = pd.to_datetime(df['trade_date'])
                self.stock_data = df
                print(f"获取到 {len(df)} 只股票的数据")
                return df
            else:
                print(f"{target_date} 无数据（可能是非交易日）")
                return pd.DataFrame()
                
        except Exception as e:
            print(f"获取单日数据失败: {e}")
            return pd.DataFrame()
    
    def screen_by_conditions(self, conditions_dict):
        """
        根据多种条件筛选股票
        conditions_dict: 包含筛选条件的字典
        """
        if self.stock_data is None or self.stock_data.empty:
            print("请先获取股票数据")
            return None
        
        df = self.stock_data.copy()
        result = df.copy()
        
        print("=== 开始条件筛选 ===")
        
        # 日期筛选
        if 'date' in conditions_dict:
            date_cond = conditions_dict['date']
            if 'specific_date' in date_cond:
                specific_date = pd.to_datetime(date_cond['specific_date'])
                result = result[result['trade_date'] == specific_date]
                print(f"筛选日期: {specific_date.strftime('%Y-%m-%d')}")
            elif 'date_range' in date_cond:
                start_date, end_date = date_cond['date_range']
                start_date = pd.to_datetime(start_date)
                end_date = pd.to_datetime(end_date)
                result = result[(result['trade_date'] >= start_date) & (result['trade_date'] <= end_date)]
                print(f"筛选日期范围: {start_date.strftime('%Y-%m-%d')} 到 {end_date.strftime('%Y-%m-%d')}")
        
        # 价格筛选
        if 'price' in conditions_dict:
            price_cond = conditions_dict['price']
            if 'min_open' in price_cond:
                result = result[result['open'] >= price_cond['min_open']]
                print(f"开盘价 >= {price_cond['min_open']}")
            if 'max_open' in price_cond:
                result = result[result['open'] <= price_cond['max_open']]
                print(f"开盘价 <= {price_cond['max_open']}")
            if 'min_close' in price_cond:
                result = result[result['close'] >= price_cond['min_close']]
                print(f"收盘价 >= {price_cond['min_close']}")
            if 'max_close' in price_cond:
                result = result[result['close'] <= price_cond['max_close']]
                print(f"收盘价 <= {price_cond['max_close']}")
        
        # 涨跌幅筛选
        if 'pct_chg' in conditions_dict:
            pct_cond = conditions_dict['pct_chg']
            if 'min_pct' in pct_cond:
                result = result[result['pct_chg'] >= pct_cond['min_pct']]
                print(f"涨跌幅 >= {pct_cond['min_pct']}%")
            if 'max_pct' in pct_cond:
                result = result[result['pct_chg'] <= pct_cond['max_pct']]
                print(f"涨跌幅 <= {pct_cond['max_pct']}%")
            if 'direction' in pct_cond:
                if pct_cond['direction'] == 'up':
                    result = result[result['pct_chg'] > 0]
                    print("筛选上涨股票")
                elif pct_cond['direction'] == 'down':
                    result = result[result['pct_chg'] < 0]
                    print("筛选下跌股票")
        
        # 成交量筛选
        if 'volume' in conditions_dict:
            vol_cond = conditions_dict['volume']
            if 'min_vol' in vol_cond:
                result = result[result['vol'] >= vol_cond['min_vol']]
                print(f"成交量 >= {vol_cond['min_vol']}手")
            if 'max_vol' in vol_cond:
                result = result[result['vol'] <= vol_cond['max_vol']]
                print(f"成交量 <= {vol_cond['max_vol']}手")
        
        print(f"筛选结果: {len(result)} 条记录")
        return result
    
    def get_top_stocks(self, date, sort_by='pct_chg', top_n=20, ascending=False):
        """
        获取某日排名靠前的股票
        """
        try:
            # 获取指定日期的数据
            daily_data = self.stock_data[self.stock_data['trade_date'] == pd.to_datetime(date)]
            
            if daily_data.empty:
                print(f"{date} 无数据")
                return pd.DataFrame()
            
            # 排序
            sorted_data = daily_data.sort_values(by=sort_by, ascending=ascending)
            top_stocks = sorted_data.head(top_n)
            
            print(f"{date} 按{sort_by}排序前{top_n}名:")
            return top_stocks
            
        except Exception as e:
            print(f"获取排名数据失败: {e}")
            return pd.DataFrame()
    
    def analyze_market(self, target_date):
        """
        分析市场整体情况
        """
        daily_data = self.stock_data[self.stock_data['trade_date'] == pd.to_datetime(target_date)]
        
        if daily_data.empty:
            print(f"{target_date} 无数据")
            return
        
        print(f"\n=== {target_date} 市场分析 ===")
        print(f"总股票数量: {len(daily_data)}")
        print(f"上涨股票数量: {len(daily_data[daily_data['pct_chg'] > 0])}")
        print(f"下跌股票数量: {len(daily_data[daily_data['pct_chg'] < 0])}")
        print(f"平盘股票数量: {len(daily_data[daily_data['pct_chg'] == 0])}")
        print(f"平均涨跌幅: {daily_data['pct_chg'].mean():.2f}%")
        print(f"最大涨幅: {daily_data['pct_chg'].max():.2f}%")
        print(f"最大跌幅: {daily_data['pct_chg'].min():.2f}%")
        print(f"平均成交量: {daily_data['vol'].mean():.0f}手")

def save_results(result_df, filename):
    """
    保存结果到CSV文件
    """
    if result_df is not None and not result_df.empty:
        if not filename.endswith('.csv'):
            filename += '.csv'
        
        result_df.to_csv(filename, index=False, encoding='utf-8-sig')
        print(f"结果已保存到 {filename}")
        return True
    else:
        print("没有数据可保存")
        return False

def main_demo():
    """
    主演示函数
    """
    screener = FullStockScreener()
    
    # 设置时间范围（建议不要范围太大，避免数据量过大）
    end_date = datetime.now().strftime('%Y%m%d')
    start_date = (datetime.now() - timedelta(days=5)).strftime('%Y%m%d')  # 最近5天
    
    print("=== 全市场股票筛选系统 ===\n")
    
    # 方式1：获取最近一个交易日的全市场数据（推荐，速度快）
    print("方式1: 获取最近交易日全市场数据")
    latest_date = end_date
    data = screener.get_single_date_data(latest_date)
    
    if data.empty:
        # 方式2：如果单日获取失败，使用分批获取
        print("\n方式2: 分批获取多日数据")
        data = screener.get_all_stocks_daily_data(start_date, end_date, batch_size=30)
    
    if data.empty:
        print("数据获取失败，程序结束")
        return
    
    # 演示各种筛选条件
    print("\n" + "="*50)
    
    # 1. 筛选大涨股票
    print("1. 筛选涨幅超过5%的股票")
    conditions = {
        'date': {'specific_date': latest_date},
        'pct_chg': {'min_pct': 5.0, 'direction': 'up'}
    }
    result1 = screener.screen_by_conditions(conditions)
    
    if not result1.empty:
        print(f"找到 {len(result1)} 只大涨股票")
        # 显示前10名
        top_10 = result1.sort_values('pct_chg', ascending=False).head(10)
        print(top_10[['ts_code', 'open', 'close', 'pct_chg', 'vol']].to_string(index=False))
        save_results(result1, '大涨股票')
    
    print("\n" + "="*50)
    
    # 2. 筛选低价股
    print("2. 筛选低价股（收盘价小于10元）")
    conditions = {
        'date': {'specific_date': latest_date},
        'price': {'max_close': 10}
    }
    result2 = screener.screen_by_conditions(conditions)
    
    if not result2.empty:
        print(f"找到 {len(result2)} 只低价股")
        save_results(result2, '低价股票')
    
    print("\n" + "="*50)
    
    # 3. 获取涨幅排行榜
    print("3. 涨幅排行榜前20名")
    top_gainers = screener.get_top_stocks(latest_date, 'pct_chg', 20, False)
    if not top_gainers.empty:
        print(top_gainers[['ts_code', 'open', 'close', 'pct_chg', 'vol']].to_string(index=False))
        save_results(top_gainers, '涨幅排行榜')
    
    print("\n" + "="*50)
    
    # 4. 市场分析
    print("4. 市场整体分析")
    screener.analyze_market(latest_date)

def interactive_screening():
    """
    交互式全市场筛选
    """
    screener = FullStockScreener()
    
    print("=== 交互式全市场股票筛选 ===\n")
    
    # 选择获取数据的方式
    print("请选择数据获取方式:")
    print("1. 获取最近交易日数据（推荐）")
    print("2. 获取多日数据")
    
    choice = input("请输入选择 (1-2): ")
    
    if choice == '1':
        date_str = input("请输入日期（YYYYMMDD，直接回车使用最近交易日）: ")
        if not date_str:
            date_str = datetime.now().strftime('%Y%m%d')
        
        data = screener.get_single_date_data(date_str)
    
    elif choice == '2':
        start_date = input("请输入开始日期（YYYYMMDD）: ")
        end_date = input("请输入结束日期（YYYYMMDD）: ")
        data = screener.get_all_stocks_daily_data(start_date, end_date)
    
    else:
        print("无效选择")
        return
    
    if data.empty:
        print("数据获取失败")
        return
    
    # 交互式筛选
    while True:
        print("\n请选择筛选条件:")
        print("1. 按涨跌幅筛选")
        print("2. 按价格筛选")
        print("3. 按成交量筛选")
        print("4. 涨幅排行榜")
        print("5. 市场分析")
        print("6. 退出")
        
        choice = input("请输入选择 (1-6): ")
        
        if choice == '1':
            min_pct = input("最小涨跌幅%（直接回车跳过）: ")
            max_pct = input("最大涨跌幅%（直接回车跳过）: ")
            direction = input("方向（1.上涨 2.下跌 3.不限）: ")
            
            conditions = {'pct_chg': {}}
            if min_pct:
                conditions['pct_chg']['min_pct'] = float(min_pct)
            if max_pct:
                conditions['pct_chg']['max_pct'] = float(max_pct)
            if direction == '1':
                conditions['pct_chg']['direction'] = 'up'
            elif direction == '2':
                conditions['pct_chg']['direction'] = 'down'
            
            result = screener.screen_by_conditions(conditions)
            if not result.empty:
                print(f"找到 {len(result)} 只股票")
                save_results(result, '涨跌幅筛选结果')
        
        elif choice == '2':
            min_price = input("最低价（直接回车跳过）: ")
            max_price = input("最高价（直接回车跳过）: ")
            
            conditions = {'price': {}}
            if min_price:
                conditions['price']['min_close'] = float(min_price)
            if max_price:
                conditions['price']['max_close'] = float(max_price)
            
            result = screener.screen_by_conditions(conditions)
            if not result.empty:
                print(f"找到 {len(result)} 只股票")
                save_results(result, '价格筛选结果')
        
        elif choice == '3':
            min_vol = input("最低成交量（手，直接回车跳过）: ")
            conditions = {'volume': {}}
            if min_vol:
                conditions['volume']['min_vol'] = float(min_vol)
            
            result = screener.screen_by_conditions(conditions)
            if not result.empty:
                print(f"找到 {len(result)} 只股票")
                save_results(result, '成交量筛选结果')
        
        elif choice == '4':
            top_n = input("显示前多少名（默认20）: ") or "20"
            date_str = input("日期（YYYYMMDD，直接回车使用最近日期）: ") or datetime.now().strftime('%Y%m%d')
            
            top_stocks = screener.get_top_stocks(date_str, 'pct_chg', int(top_n), False)
            if not top_stocks.empty:
                save_results(top_stocks, '涨幅排行榜')
        
        elif choice == '5':
            date_str = input("分析日期（YYYYMMDD，直接回车使用最近日期）: ") or datetime.now().strftime('%Y%m%d')
            screener.analyze_market(date_str)
        
        elif choice == '6':
            break
        
        else:
            print("无效选择")

if __name__ == "__main__":
    # 运行演示
    main_demo()
    
    # 运行交互式模式（取消注释即可）
    # interactive_screening()