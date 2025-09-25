import tushare as ts
import pandas as pd
from datetime import datetime, timedelta
import matplotlib.pyplot as plt

# 设置token
ts.set_token('262474d8ae99f188cdd6cbb167d609535f77f4f144ca5b1e3a558a30')
pro = ts.pro_api()

class StockScreener:
    def __init__(self):
        self.stock_data = None
    
    def get_stock_daily_data(self, stock_codes, start_date, end_date):
        """
        获取多只股票的日线数据
        """
        all_data = []
        
        for i, stock_code in enumerate(stock_codes):
            try:
                # 添加延时避免请求过于频繁
                if i > 0 and i % 5 == 0:
                    import time
                    time.sleep(1)
                
                df = pro.daily(ts_code=stock_code, 
                              start_date=start_date, 
                              end_date=end_date)
                
                if not df.empty:
                    df['stock_name'] = stock_code
                    all_data.append(df)
                    print(f"✓ 成功获取 {stock_code} 数据，共 {len(df)} 条")
                else:
                    print(f"⚠ {stock_code} 无数据")
                    
            except Exception as e:
                print(f"✗ 获取 {stock_code} 失败: {e}")
        
        if all_data:
            self.stock_data = pd.concat(all_data, ignore_index=True)
            # 转换日期格式并排序
            self.stock_data['trade_date'] = pd.to_datetime(self.stock_data['trade_date'])
            self.stock_data = self.stock_data.sort_values(['ts_code', 'trade_date'])
            return self.stock_data
        else:
            return pd.DataFrame()
    
    def screen_by_date(self, specific_date=None, date_range=None):
        """
        根据交易日期筛选股票
        """
        if self.stock_data is None:
            print("请先获取股票数据")
            return None
        
        df = self.stock_data.copy()
        
        if specific_date:
            # 筛选特定日期
            if isinstance(specific_date, str):
                specific_date = pd.to_datetime(specific_date)
            result = df[df['trade_date'] == specific_date]
            print(f"筛选日期: {specific_date.strftime('%Y-%m-%d')}, 找到 {len(result)} 条记录")
        
        elif date_range:
            # 筛选日期范围
            start_date, end_date = date_range
            if isinstance(start_date, str):
                start_date = pd.to_datetime(start_date)
            if isinstance(end_date, str):
                end_date = pd.to_datetime(end_date)
            
            result = df[(df['trade_date'] >= start_date) & (df['trade_date'] <= end_date)]
            print(f"筛选日期范围: {start_date.strftime('%Y-%m-%d')} 到 {end_date.strftime('%Y-%m-%d')}, 找到 {len(result)} 条记录")
        
        else:
            print("请提供具体日期或日期范围")
            return None
        
        return result
    
    def screen_by_open_price(self, min_open=None, max_open=None, comparison_type='absolute'):
        """
        根据开盘价筛选股票
        comparison_type: 'absolute'绝对价格, 'relative'相对前日收盘价比例
        """
        if self.stock_data is None:
            print("请先获取股票数据")
            return None
        
        df = self.stock_data.copy()
        result = df.copy()
        
        conditions = []
        
        if min_open is not None:
            if comparison_type == 'relative' and 'pre_close' in df.columns:
                # 相对比例筛选（开盘价相对于前收盘价的比例）
                min_ratio = min_open / 100  # 输入百分比，如5表示5%
                condition = (df['open'] / df['pre_close'] - 1) >= min_ratio
                conditions.append(condition)
                print(f"开盘价涨幅 >= {min_open}%")
            else:
                # 绝对价格筛选
                conditions.append(df['open'] >= min_open)
                print(f"开盘价 >= {min_open}")
        
        if max_open is not None:
            if comparison_type == 'relative' and 'pre_close' in df.columns:
                max_ratio = max_open / 100
                condition = (df['open'] / df['pre_close'] - 1) <= max_ratio
                conditions.append(condition)
                print(f"开盘价涨幅 <= {max_open}%")
            else:
                conditions.append(df['open'] <= max_open)
                print(f"开盘价 <= {max_open}")
        
        if conditions:
            # 合并所有条件
            combined_condition = conditions[0]
            for condition in conditions[1:]:
                combined_condition = combined_condition & condition
            
            result = df[combined_condition]
            print(f"开盘价筛选结果: {len(result)} 条记录")
        
        return result
    
    def screen_by_change_amount(self, min_change=None, max_change=None, change_direction=None):
        """
        根据涨跌额筛选股票
        change_direction: 'up'上涨, 'down'下跌, None不限
        """
        if self.stock_data is None:
            print("请先获取股票数据")
            return None
        
        df = self.stock_data.copy()
        result = df.copy()
        
        conditions = []
        
        if change_direction == 'up':
            conditions.append(df['change'] > 0)
            print("筛选上涨股票")
        elif change_direction == 'down':
            conditions.append(df['change'] < 0)
            print("筛选下跌股票")
        
        if min_change is not None:
            conditions.append(df['change'] >= min_change)
            print(f"涨跌额 >= {min_change}")
        
        if max_change is not None:
            conditions.append(df['change'] <= max_change)
            print(f"涨跌额 <= {max_change}")
        
        if conditions:
            combined_condition = conditions[0]
            for condition in conditions[1:]:
                combined_condition = combined_condition & condition
            
            result = df[combined_condition]
            print(f"涨跌额筛选结果: {len(result)} 条记录")
        
        return result
    
    def screen_by_change_percent(self, min_pct=None, max_pct=None, pct_direction=None):
        """
        根据涨跌幅筛选股票
        pct_direction: 'up'上涨, 'down'下跌, None不限
        """
        if self.stock_data is None:
            print("请先获取股票数据")
            return None
        
        df = self.stock_data.copy()
        result = df.copy()
        
        conditions = []
        
        if pct_direction == 'up':
            conditions.append(df['pct_chg'] > 0)
            print("筛选上涨股票")
        elif pct_direction == 'down':
            conditions.append(df['pct_chg'] < 0)
            print("筛选下跌股票")
        
        if min_pct is not None:
            conditions.append(df['pct_chg'] >= min_pct)
            print(f"涨跌幅 >= {min_pct}%")
        
        if max_pct is not None:
            conditions.append(df['pct_chg'] <= max_pct)
            print(f"涨跌幅 <= {max_pct}%")
        
        if conditions:
            combined_condition = conditions[0]
            for condition in conditions[1:]:
                combined_condition = combined_condition & condition
            
            result = df[combined_condition]
            print(f"涨跌幅筛选结果: {len(result)} 条记录")
        
        return result
    
    def comprehensive_screen(self, date_criteria=None, open_criteria=None, 
                           change_amount_criteria=None, change_percent_criteria=None):
        """
        综合筛选：同时应用多个条件
        """
        if self.stock_data is None:
            print("请先获取股票数据")
            return None
        
        df = self.stock_data.copy()
        result = df.copy()
        
        print("=== 开始综合筛选 ===")
        
        # 日期筛选
        if date_criteria:
            if 'specific_date' in date_criteria:
                temp_result = self.screen_by_date(specific_date=date_criteria['specific_date'])
            elif 'date_range' in date_criteria:
                temp_result = self.screen_by_date(date_range=date_criteria['date_range'])
            
            if temp_result is not None and not temp_result.empty:
                result = result[result.index.isin(temp_result.index)]
        
        # 开盘价筛选
        if open_criteria:
            temp_result = self.screen_by_open_price(
                min_open=open_criteria.get('min_open'),
                max_open=open_criteria.get('max_open'),
                comparison_type=open_criteria.get('comparison_type', 'absolute')
            )
            if temp_result is not None and not temp_result.empty:
                result = result[result.index.isin(temp_result.index)]
        
        # 涨跌额筛选
        if change_amount_criteria:
            temp_result = self.screen_by_change_amount(
                min_change=change_amount_criteria.get('min_change'),
                max_change=change_amount_criteria.get('max_change'),
                change_direction=change_amount_criteria.get('change_direction')
            )
            if temp_result is not None and not temp_result.empty:
                result = result[result.index.isin(temp_result.index)]
        
        # 涨跌幅筛选
        if change_percent_criteria:
            temp_result = self.screen_by_change_percent(
                min_pct=change_percent_criteria.get('min_pct'),
                max_pct=change_percent_criteria.get('max_pct'),
                pct_direction=change_percent_criteria.get('pct_direction')
            )
            if temp_result is not None and not temp_result.empty:
                result = result[result.index.isin(temp_result.index)]
        
        print(f"综合筛选结果: {len(result)} 条记录")
        return result
    
    def display_results(self, result_df, max_display=10):
        """
        显示筛选结果
        """
        if result_df is None or result_df.empty:
            print("没有找到符合条件的股票")
            return
        
        display_columns = ['ts_code', 'trade_date', 'open', 'high', 'low', 'close', 'change', 'pct_chg', 'vol']
        available_columns = [col for col in display_columns if col in result_df.columns]
        
        print(f"\n筛选结果 (显示前{min(max_display, len(result_df))}条):")
        print("=" * 100)
        print(result_df[available_columns].head(max_display).to_string(index=False))
        print("=" * 100)
        
        # 统计信息
        if 'pct_chg' in result_df.columns:
            print(f"\n统计信息:")
            print(f"平均涨跌幅: {result_df['pct_chg'].mean():.2f}%")
            print(f"最大涨跌幅: {result_df['pct_chg'].max():.2f}%")
            print(f"最小涨跌幅: {result_df['pct_chg'].min():.2f}%")
            print(f"上涨股票数量: {len(result_df[result_df['pct_chg'] > 0])}")
            print(f"下跌股票数量: {len(result_df[result_df['pct_chg'] < 0])}")

def main():
    """
    主函数演示各种筛选功能
    """
    screener = StockScreener()
    
    # 定义股票列表
    stock_list = ['000001.SZ', '000002.SZ', '600036.SH', '601318.SH', 
                  '000858.SZ', '600519.SH', '000333.SZ', '600887.SH']
    
    # 获取最近30天的数据
    end_date = datetime.now().strftime('%Y%m%d')
    start_date = (datetime.now() - timedelta(days=30)).strftime('%Y%m%d')
    
    print("正在获取股票数据...")
    data = screener.get_stock_daily_data(stock_list, start_date, end_date)
    
    if data.empty:
        print("获取数据失败，程序结束")
        return
    
    print(f"\n成功获取 {len(stock_list)} 只股票共 {len(data)} 条日线数据")
    
    # 演示各种筛选方式
    while True:
        print("\n" + "="*60)
        print("请选择筛选方式:")
        print("1. 按交易日期筛选")
        print("2. 按开盘价筛选")
        print("3. 按涨跌额筛选")
        print("4. 按涨跌幅筛选")
        print("5. 综合筛选")
        print("6. 退出")
        
        choice = input("请输入选择 (1-6): ").strip()
        
        if choice == '1':
            # 日期筛选
            print("\n日期筛选选项:")
            print("1. 特定日期")
            print("2. 日期范围")
            date_choice = input("请选择: ").strip()
            
            if date_choice == '1':
                date_str = input("请输入日期 (格式: YYYYMMDD 或 YYYY-MM-DD): ")
                result = screener.screen_by_date(specific_date=date_str)
            elif date_choice == '2':
                start_str = input("请输入开始日期: ")
                end_str = input("请输入结束日期: ")
                result = screener.screen_by_date(date_range=(start_str, end_str))
            else:
                continue
                
        elif choice == '2':
            # 开盘价筛选
            print("\n开盘价筛选:")
            min_open = input("最小开盘价 (直接回车跳过): ")
            max_open = input("最大开盘价 (直接回车跳过): ")
            comp_type = input("筛选类型 (1.绝对价格 2.相对涨幅百分比): ")
            
            min_open = float(min_open) if min_open else None
            max_open = float(max_open) if max_open else None
            comp_type = 'relative' if comp_type == '2' else 'absolute'
            
            result = screener.screen_by_open_price(min_open, max_open, comp_type)
            
        elif choice == '3':
            # 涨跌额筛选
            print("\n涨跌额筛选:")
            min_change = input("最小涨跌额 (直接回车跳过): ")
            max_change = input("最大涨跌额 (直接回车跳过): ")
            direction = input("方向 (1.上涨 2.下跌 3.不限): ")
            
            min_change = float(min_change) if min_change else None
            max_change = float(max_change) if max_change else None
            direction_map = {'1': 'up', '2': 'down', '3': None}
            direction = direction_map.get(direction)
            
            result = screener.screen_by_change_amount(min_change, max_change, direction)
            
        elif choice == '4':
            # 涨跌幅筛选
            print("\n涨跌幅筛选:")
            min_pct = input("最小涨跌幅% (直接回车跳过): ")
            max_pct = input("最大涨跌幅% (直接回车跳过): ")
            direction = input("方向 (1.上涨 2.下跌 3.不限): ")
            
            min_pct = float(min_pct) if min_pct else None
            max_pct = float(max_pct) if max_pct else None
            direction_map = {'1': 'up', '2': 'down', '3': None}
            direction = direction_map.get(direction)
            
            result = screener.screen_by_change_percent(min_pct, max_pct, direction)
            
        elif choice == '5':
            # 综合筛选示例
            print("\n综合筛选示例: 寻找近期大涨的股票")
            result = screener.comprehensive_screen(
                date_criteria={'date_range': ('20240101', end_date)},
                change_percent_criteria={'min_pct': 5.0, 'pct_direction': 'up'}
            )
            
        elif choice == '6':
            print("程序退出")
            break
        else:
            print("无效选择，请重新输入")
            continue
        
        # 显示结果
        if 'result' in locals():
            screener.display_results(result)
            
            # 询问是否保存结果
            save = input("\n是否保存结果到文件? (y/n): ").lower()
            if save == 'y':
                filename = input("请输入文件名 (不含扩展名): ")
                result.to_csv(f'{filename}.csv', index=False, encoding='utf-8-sig')
                result.to_excel(f'{filename}.xlsx', index=False)
                print(f"结果已保存到 {filename}.csv 和 {filename}.xlsx")

if __name__ == "__main__":
    main()