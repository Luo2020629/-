import tushare as ts
import pandas as pd
from datetime import datetime, timedelta
import time
import os

# 设置token
ts.set_token('d58ad304d9b289df2c68fc978db31210458472e724b04e657f7ea01a')  # 请替换为你的实际token
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
            df = pro.stock_basic(exchange='', list_status='L', 
                                fields='ts_code,symbol,name,area,industry,list_date,market')
            self.all_stocks = df['ts_code'].tolist()
            print(f"获取到 {len(self.all_stocks)} 只正常上市的股票")
            return self.all_stocks
        except Exception as e:
            print(f"获取股票列表失败: {e}")
            return []
    
    def get_single_date_data(self, target_date):
        """
        获取特定日期的全市场数据（高效方法）
        """
        try:
            print(f"正在获取 {target_date} 的全市场日线数据...")
            
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
    
    def get_multiple_days_data(self, start_date, end_date, batch_size=30):
        """
        分批获取多日数据
        """
        if self.all_stocks is None:
            self.get_all_stock_list()
        
        if not self.all_stocks:
            return pd.DataFrame()
        
        all_data = []
        total_stocks = len(self.all_stocks)
        
        print(f"开始分批获取 {total_stocks} 只股票的日线数据...")
        print(f"时间范围: {start_date} 到 {end_date}")
        
        for i in range(0, total_stocks, batch_size):
            batch = self.all_stocks[i:i + batch_size]
            batch_num = i // batch_size + 1
            total_batches = (total_stocks + batch_size - 1) // batch_size
            
            print(f"正在获取第 {batch_num}/{total_batches} 批数据...")
            
            batch_data = []
            for j, stock_code in enumerate(batch):
                try:
                    if j > 0 and j % 10 == 0:
                        time.sleep(1)
                    
                    df = pro.daily(ts_code=stock_code, 
                                  start_date=start_date, 
                                  end_date=end_date)
                    
                    if not df.empty:
                        batch_data.append(df)
                    else:
                        print(f"  ⚠ {stock_code} 无数据")
                        
                except Exception as e:
                    print(f"  ✗ {stock_code} 获取失败")
                    continue
            
            if batch_data:
                batch_df = pd.concat(batch_data, ignore_index=True)
                all_data.append(batch_df)
            
            if i + batch_size < total_stocks:
                time.sleep(2)
        
        if all_data:
            self.stock_data = pd.concat(all_data, ignore_index=True)
            self.stock_data['trade_date'] = pd.to_datetime(self.stock_data['trade_date'])
            self.stock_data = self.stock_data.sort_values(['ts_code', 'trade_date'])
            
            print(f"\n数据获取完成！共 {len(self.stock_data)} 条记录")
            return self.stock_data
        else:
            return pd.DataFrame()
    
    def screen_by_conditions(self, conditions_dict):
        """
        根据条件筛选股票
        """
        if self.stock_data is None:
            print("请先获取股票数据")
            return None
        
        df = self.stock_data.copy()
        result = df
        
        print("\n正在应用筛选条件...")
        
        # 日期筛选
        if 'date' in conditions_dict:
            date_cond = conditions_dict['date']
            if 'specific_date' in date_cond:
                specific_date = pd.to_datetime(date_cond['specific_date'])
                result = result[result['trade_date'] == specific_date]
                print(f"📅 日期: {specific_date.strftime('%Y-%m-%d')}")
        
        # 价格筛选
        if 'price' in conditions_dict:
            price_cond = conditions_dict['price']
            if 'min_open' in price_cond:
                result = result[result['open'] >= price_cond['min_open']]
                print(f"💰 开盘价 >= {price_cond['min_open']}")
            if 'max_open' in price_cond:
                result = result[result['open'] <= price_cond['max_open']]
                print(f"💰 开盘价 <= {price_cond['max_open']}")
            if 'min_close' in price_cond:
                result = result[result['close'] >= price_cond['min_close']]
                print(f"💰 收盘价 >= {price_cond['min_close']}")
            if 'max_close' in price_cond:
                result = result[result['close'] <= price_cond['max_close']]
                print(f"💰 收盘价 <= {price_cond['max_close']}")
        
        # 涨跌幅筛选
        if 'pct_chg' in conditions_dict:
            pct_cond = conditions_dict['pct_chg']
            if 'min_pct' in pct_cond:
                result = result[result['pct_chg'] >= pct_cond['min_pct']]
                print(f"📈 涨跌幅 >= {pct_cond['min_pct']}%")
            if 'max_pct' in pct_cond:
                result = result[result['pct_chg'] <= pct_cond['max_pct']]
                print(f"📈 涨跌幅 <= {pct_cond['max_pct']}%")
            if 'direction' in pct_cond:
                if pct_cond['direction'] == 'up':
                    result = result[result['pct_chg'] > 0]
                    print("📈 筛选上涨股票")
                elif pct_cond['direction'] == 'down':
                    result = result[result['pct_chg'] < 0]
                    print("📉 筛选下跌股票")
        
        # 成交量筛选
        if 'volume' in conditions_dict:
            vol_cond = conditions_dict['volume']
            if 'min_vol' in vol_cond:
                result = result[result['vol'] >= vol_cond['min_vol']]
                print(f"📊 成交量 >= {vol_cond['min_vol']}手")
        
        print(f"✅ 筛选完成！找到 {len(result)} 条记录")
        return result
    
    def get_top_stocks(self, date, sort_by='pct_chg', top_n=20, ascending=False):
        """
        获取排行榜
        """
        try:
            daily_data = self.stock_data[self.stock_data['trade_date'] == pd.to_datetime(date)]
            
            if daily_data.empty:
                print(f"{date} 无数据")
                return pd.DataFrame()
            
            sorted_data = daily_data.sort_values(by=sort_by, ascending=ascending)
            return sorted_data.head(top_n)
            
        except Exception as e:
            print(f"获取排名数据失败: {e}")
            return pd.DataFrame()
    
    def analyze_market(self, target_date):
        """
        市场分析
        """
        daily_data = self.stock_data[self.stock_data['trade_date'] == pd.to_datetime(target_date)]
        
        if daily_data.empty:
            print(f"{target_date} 无数据")
            return
        
        print(f"\n📊 {target_date} 市场分析报告")
        print("="*50)
        print(f"📈 总股票数量: {len(daily_data)}")
        print(f"🟢 上涨股票: {len(daily_data[daily_data['pct_chg'] > 0])}")
        print(f"🔴 下跌股票: {len(daily_data[daily_data['pct_chg'] < 0])}")
        print(f"⚪ 平盘股票: {len(daily_data[daily_data['pct_chg'] == 0])}")
        print(f"📊 平均涨跌幅: {daily_data['pct_chg'].mean():.2f}%")
        print(f"🚀 最大涨幅: {daily_data['pct_chg'].max():.2f}%")
        print(f"💥 最大跌幅: {daily_data['pct_chg'].min():.2f}%")
        print(f"💰 平均成交量: {daily_data['vol'].mean():.0f}手")

def save_results(result_df, filename):
    """
    保存结果
    """
    if result_df is not None and not result_df.empty:
        if not filename.endswith('.csv'):
            filename += '.csv'
        
        result_df.to_csv(filename, index=False, encoding='utf-8-sig')
        print(f"💾 结果已保存到 {filename}")
        return True
    else:
        print("❌ 没有数据可保存")
        return False

def display_results(result_df, max_display=15):
    """
    显示结果
    """
    if result_df is None or result_df.empty:
        print("❌ 没有找到符合条件的股票")
        return
    
    display_columns = ['ts_code', 'trade_date', 'open', 'close', 'pct_chg', 'vol']
    available_columns = [col for col in display_columns if col in result_df.columns]
    
    print(f"\n📋 筛选结果 (显示前{min(max_display, len(result_df))}条):")
    print("="*80)
    print(result_df[available_columns].head(max_display).to_string(index=False))
    print("="*80)

def interactive_screening():
    """
    交互式全市场筛选主界面
    """
    screener = FullStockScreener()
    
    print("🎯" + "="*50)
    print("           沪深A股全市场股票筛选系统")
    print("="*50)
    
    while True:
        print("\n📊 请选择数据获取方式:")
        print("1. 获取单日全市场数据（推荐，速度快）")
        print("2. 获取多日历史数据（数据量大，速度慢）")
        print("3. 退出系统")
        
        choice = input("🖊️  请输入选择 (1-3): ").strip()
        
        if choice == '1':
            single_date_mode(screener)
        elif choice == '2':
            multiple_days_mode(screener)
        elif choice == '3':
            print("👋 感谢使用，再见！")
            break
        else:
            print("❌ 无效选择，请重新输入")

def single_date_mode(screener):
    """
    单日数据模式
    """
    date_str = input("📅 请输入日期（YYYYMMDD，回车使用今天）: ").strip()
    if not date_str:
        date_str = datetime.now().strftime('%Y%m%d')
    
    data = screener.get_single_date_data(date_str)
    
    if data.empty:
        print("❌ 数据获取失败，请检查日期格式或网络连接")
        return
    
    screening_loop(screener, date_str)

def multiple_days_mode(screener):
    """
    多日数据模式
    """
    start_date = input("📅 请输入开始日期（YYYYMMDD）: ").strip()
    end_date = input("📅 请输入结束日期（YYYYMMDD）: ").strip()
    
    if not start_date or not end_date:
        print("❌ 请输入有效的日期")
        return
    
    data = screener.get_multiple_days_data(start_date, end_date)
    
    if data.empty:
        print("❌ 数据获取失败")
        return
    
    screening_loop(screener, f"{start_date}到{end_date}")

def screening_loop(screener, date_info):
    """
    筛选循环
    """
    while True:
        print(f"\n🎯 当前数据: {date_info}")
        print("请选择筛选功能:")
        print("1. 按涨跌幅筛选")
        print("2. 按价格筛选")
        print("3. 按成交量筛选")
        print("4. 查看涨幅排行榜")
        print("5. 查看跌幅排行榜")
        print("6. 市场分析报告")
        print("7. 返回主菜单")
        
        choice = input("🖊️  请输入选择 (1-7): ").strip()
        
        if choice == '1':
            pct_screening(screener)
        elif choice == '2':
            price_screening(screener)
        elif choice == '3':
            volume_screening(screener)
        elif choice == '4':
            top_gainers(screener)
        elif choice == '5':
            top_losers(screener)
        elif choice == '6':
            market_analysis(screener)
        elif choice == '7':
            break
        else:
            print("❌ 无效选择")

def pct_screening(screener):
    """
    涨跌幅筛选
    """
    print("\n📈 涨跌幅筛选")
    min_pct = input("最小涨跌幅%（回车跳过）: ").strip()
    max_pct = input("最大涨跌幅%（回车跳过）: ").strip()
    direction = input("方向（1.上涨 2.下跌 3.不限）: ").strip()
    
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
    display_results(result)
    
    if not result.empty:
        save = input("💾 是否保存结果？(y/n): ").strip().lower()
        if save == 'y':
            filename = input("📁 请输入文件名: ").strip()
            save_results(result, filename)

def price_screening(screener):
    """
    价格筛选
    """
    print("\n💰 价格筛选")
    min_price = input("最低价（元，回车跳过）: ").strip()
    max_price = input("最高价（元，回车跳过）: ").strip()
    price_type = input("价格类型（1.开盘价 2.收盘价）: ").strip()
    
    conditions = {'price': {}}
    if min_price:
        if price_type == '1':
            conditions['price']['min_open'] = float(min_price)
        else:
            conditions['price']['min_close'] = float(min_price)
    if max_price:
        if price_type == '1':
            conditions['price']['max_open'] = float(max_price)
        else:
            conditions['price']['max_close'] = float(max_price)
    
    result = screener.screen_by_conditions(conditions)
    display_results(result)
    
    if not result.empty:
        save = input("💾 是否保存结果？(y/n): ").strip().lower()
        if save == 'y':
            filename = input("📁 请输入文件名: ").strip()
            save_results(result, filename)

def volume_screening(screener):
    """
    成交量筛选
    """
    print("\n📊 成交量筛选")
    min_vol = input("最低成交量（手，回车跳过）: ").strip()
    
    conditions = {'volume': {}}
    if min_vol:
        conditions['volume']['min_vol'] = float(min_vol)
    
    result = screener.screen_by_conditions(conditions)
    display_results(result)
    
    if not result.empty:
        save = input("💾 是否保存结果？(y/n): ").strip().lower()
        if save == 'y':
            filename = input("📁 请输入文件名: ").strip()
            save_results(result, filename)

def top_gainers(screener):
    """
    涨幅榜
    """
    print("\n🚀 涨幅排行榜")
    top_n = input("显示前多少名（默认20）: ").strip() or "20"
    date_str = input("日期（YYYYMMDD，回车使用最近日期）: ").strip()
    
    if not date_str and screener.stock_data is not None:
        date_str = screener.stock_data['trade_date'].max().strftime('%Y%m%d')
    
    top_stocks = screener.get_top_stocks(date_str, 'pct_chg', int(top_n), False)
    display_results(top_stocks, int(top_n))
    
    if not top_stocks.empty:
        save = input("💾 是否保存排行榜？(y/n): ").strip().lower()
        if save == 'y':
            save_results(top_stocks, f'涨幅排行榜_{date_str}')

def top_losers(screener):
    """
    跌幅榜
    """
    print("\n💥 跌幅排行榜")
    top_n = input("显示前多少名（默认20）: ").strip() or "20"
    date_str = input("日期（YYYYMMDD，回车使用最近日期）: ").strip()
    
    if not date_str and screener.stock_data is not None:
        date_str = screener.stock_data['trade_date'].max().strftime('%Y%m%d')
    
    top_stocks = screener.get_top_stocks(date_str, 'pct_chg', int(top_n), True)
    display_results(top_stocks, int(top_n))
    
    if not top_stocks.empty:
        save = input("💾 是否保存排行榜？(y/n): ").strip().lower()
        if save == 'y':
            save_results(top_stocks, f'跌幅排行榜_{date_str}')

def market_analysis(screener):
    """
    市场分析
    """
    date_str = input("📅 分析日期（YYYYMMDD，回车使用最近日期）: ").strip()
    
    if not date_str and screener.stock_data is not None:
        date_str = screener.stock_data['trade_date'].max().strftime('%Y%m%d')
    
    screener.analyze_market(date_str)

if __name__ == "__main__":
    # 直接启动交互式界面
    interactive_screening()