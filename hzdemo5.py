import tushare as ts
import pandas as pd
from datetime import datetime, timedelta
import time
import os
import concurrent.futures
from tqdm import tqdm
import requests
import threading
from collections import deque

# 设置token
ts.set_token('262474d8ae99f188cdd6cbb167d609535f77f4f144ca5b1e3a558a30')
pro = ts.pro_api()

class RateLimiter:
    """请求频率限制器"""
    def __init__(self, max_calls_per_minute=50):
        self.max_calls_per_minute = max_calls_per_minute
        self.calls = deque()
        self.lock = threading.Lock()
    
    def wait_if_needed(self):
        """如果需要等待，则阻塞直到可以继续请求"""
        with self.lock:
            now = time.time()
            # 移除1分钟前的记录
            while self.calls and self.calls[0] < now - 60:
                self.calls.popleft()
            
            # 如果达到限制，等待
            if len(self.calls) >= self.max_calls_per_minute:
                wait_time = 60 - (now - self.calls[0])
                if wait_time > 0:
                    print(f"⏳ 频率限制：等待{wait_time:.1f}秒后继续...")
                    time.sleep(wait_time)
                    # 等待后重新清理记录
                    now = time.time()
                    while self.calls and self.calls[0] < now - 60:
                        self.calls.popleft()
            
            # 记录本次请求时间
            self.calls.append(now)
    
    def get_remaining_calls(self):
        """获取剩余可调用次数"""
        with self.lock:
            now = time.time()
            # 移除1分钟前的记录
            while self.calls and self.calls[0] < now - 60:
                self.calls.popleft()
            return max(0, self.max_calls_per_minute - len(self.calls))
    
    def reset(self):
        """重置计数器"""
        with self.lock:
            self.calls.clear()

class OptimizedStockScreener:
    def __init__(self):
        self.stock_data = None
        self.all_stocks = None
        self.max_workers = 10  # 提高并发数，因为每批正好50只
        self.retry_times = 3
        self.request_delay = 0.3  # 降低延迟，因为批次间会等待
        self.rate_limiter = RateLimiter(max_calls_per_minute=50)
        self.batch_size = 50  # 每批50只股票，正好匹配API限制
    
    def get_all_stock_list(self):
        """
        获取沪深所有正常上市的股票列表（带缓存）
        """
        try:
            # 应用频率限制
            self.rate_limiter.wait_if_needed()
            
            # 尝试从缓存文件读取
            cache_file = 'stock_list_cache.csv'
            if os.path.exists(cache_file):
                cache_time = os.path.getmtime(cache_file)
                # 缓存有效期1天
                if time.time() - cache_time < 24 * 3600:
                    df = pd.read_csv(cache_file)
                    self.all_stocks = df['ts_code'].tolist()
                    print(f"📁 从缓存读取 {len(self.all_stocks)} 只股票列表")
                    return self.all_stocks
            
            # 从API获取
            df = pro.stock_basic(exchange='', list_status='L', 
                                fields='ts_code,symbol,name,area,industry,list_date,market')
            self.all_stocks = df['ts_code'].tolist()
            
            # 保存到缓存
            df.to_csv(cache_file, index=False)
            print(f"✅ 获取到 {len(self.all_stocks)} 只正常上市的股票")
            return self.all_stocks
            
        except Exception as e:
            print(f"❌ 获取股票列表失败: {e}")
            return []
    
    def get_single_stock_data(self, stock_code, start_date, end_date):
        """
        获取单只股票数据（带重试机制和频率限制）
        """
        for attempt in range(self.retry_times):
            try:
                # 应用频率限制
                self.rate_limiter.wait_if_needed()
                
                # 添加请求延迟
                time.sleep(self.request_delay)
                
                df = pro.daily(ts_code=stock_code, 
                              start_date=start_date, 
                              end_date=end_date)
                
                if not df.empty:
                    return df
                else:
                    return None
                    
            except requests.exceptions.RequestException as e:
                remaining = self.rate_limiter.get_remaining_calls()
                print(f"   ⚠ {stock_code} 网络错误(尝试{attempt+1}/{self.retry_times}, 剩余{remaining}次/分钟): {e}")
                if attempt < self.retry_times - 1:
                    time.sleep(2)
            except Exception as e:
                remaining = self.rate_limiter.get_remaining_calls()
                print(f"   ❌ {stock_code} 获取失败(尝试{attempt+1}/{self.retry_times}, 剩余{remaining}次/分钟): {e}")
                break
                
        return None
    
    def get_multiple_days_data(self, start_date, end_date):
        """
        分批获取多日数据（50只股票一批，优化版）
        """
        if self.all_stocks is None:
            self.get_all_stock_list()
        
        if not self.all_stocks:
            return pd.DataFrame()
        
        total_stocks = len(self.all_stocks)
        batch_size = self.batch_size
        total_batches = (total_stocks + batch_size - 1) // batch_size
        
        print(f"🚀 开始获取 {total_stocks} 只股票的日线数据...")
        print(f"📅 时间范围: {start_date} 到 {end_date}")
        print(f"📊 分批策略: {batch_size}只股票/批，共{total_batches}批")
        print(f"⚡ 并发数: {self.max_workers}, 重试次数: {self.retry_times}")
        print(f"🎯 频率限制: 每分钟最多 {self.rate_limiter.max_calls_per_minute} 次请求")
        
        all_data = []
        successful_stocks = 0
        failed_stocks = []
        
        # 计算预计时间（每批约1分钟）
        estimated_minutes = total_batches
        print(f"⏱️ 预计需要时间: {estimated_minutes} 分钟")
        
        # 使用进度条显示进度（按批次）
        pbar = tqdm(total=total_batches, desc="批次进度")
        
        try:
            # 按50只股票一批进行处理
            for batch_num in range(total_batches):
                start_idx = batch_num * batch_size
                end_idx = min((batch_num + 1) * batch_size, total_stocks)
                batch = self.all_stocks[start_idx:end_idx]
                
                print(f"\n🎯 第 {batch_num + 1}/{total_batches} 批 ({len(batch)} 只股票)...")
                print(f"   📋 股票范围: {batch[0]} 到 {batch[-1]}")
                
                # 重置频率限制器（每批开始时）
                if batch_num == 0:
                    self.rate_limiter.reset()
                
                batch_results = []
                batch_successful = 0
                batch_failed = []
                
                # 使用线程池并发获取本批股票
                with concurrent.futures.ThreadPoolExecutor(max_workers=min(self.max_workers, len(batch))) as executor:
                    # 提交本批所有任务
                    future_to_stock = {
                        executor.submit(self.get_single_stock_data, stock, start_date, end_date): stock 
                        for stock in batch
                    }
                    
                    # 处理本批完成的任务
                    for future in concurrent.futures.as_completed(future_to_stock):
                        stock_code = future_to_stock[future]
                        try:
                            result = future.result(timeout=45)
                            if result is not None:
                                batch_results.append(result)
                                batch_successful += 1
                                successful_stocks += 1
                            else:
                                batch_failed.append(stock_code)
                                failed_stocks.append(stock_code)
                            
                        except concurrent.futures.TimeoutError:
                            print(f"   ⏰ {stock_code} 请求超时")
                            batch_failed.append(stock_code)
                            failed_stocks.append(stock_code)
                        except Exception as e:
                            print(f"   ❌ {stock_code} 处理异常: {e}")
                            batch_failed.append(stock_code)
                            failed_stocks.append(stock_code)
                
                # 合并本批次数据
                if batch_results:
                    try:
                        batch_df = pd.concat(batch_results, ignore_index=True)
                        all_data.append(batch_df)
                        success_rate = batch_successful / len(batch) * 100
                        print(f"   ✅ 本批成功: {batch_successful}/{len(batch)} ({success_rate:.1f}%)")
                        
                        # 显示本批数据统计
                        trade_dates = batch_df['trade_date'].nunique()
                        print(f"   📅 本批数据: {len(batch_df)} 条记录, {trade_dates} 个交易日")
                    except Exception as e:
                        print(f"   ❌ 本批数据合并失败: {e}")
                else:
                    print(f"   ❌ 本批全部失败: 0/{len(batch)}")
                
                # 更新进度条
                pbar.update(1)
                remaining_batches = total_batches - (batch_num + 1)
                remaining_calls = self.rate_limiter.get_remaining_calls()
                pbar.set_postfix(成功股票=successful_stocks, 失败股票=len(failed_stocks), 剩余批次=remaining_batches)
                
                # 批次间等待（除非是最后一批）
                if batch_num < total_batches - 1:
                    # 计算智能等待时间
                    remaining_calls = self.rate_limiter.get_remaining_calls()
                    if remaining_calls < 10:  # 剩余次数较少时等待
                        wait_time = 60  # 等待1分钟重置限额
                    else:
                        wait_time = 5  # 短暂休息
                    
                    print(f"   ⏳ 等待{wait_time}秒后继续下一批... (剩余{remaining_calls}次/分钟)")
                    time.sleep(wait_time)
        
        finally:
            # 关闭进度条
            pbar.close()
        
        # 合并所有数据
        if all_data:
            try:
                self.stock_data = pd.concat(all_data, ignore_index=True)
                self.stock_data['trade_date'] = pd.to_datetime(self.stock_data['trade_date'])
                self.stock_data = self.stock_data.sort_values(['ts_code', 'trade_date'])
                
                # 数据质量检查
                self._check_data_quality()
                
                print(f"\n🎉 数据获取完成！")
                print(f"✅ 成功获取: {successful_stocks} 只股票")
                print(f"❌ 获取失败: {len(failed_stocks)} 只股票")
                print(f"📊 总成功率: {successful_stocks/total_stocks*100:.1f}%")
                print(f"📊 总记录数: {len(self.stock_data)} 条")
                print(f"📅 时间范围: {self.stock_data['trade_date'].min()} 到 {self.stock_data['trade_date'].max()}")
                print(f"📈 股票覆盖率: {self.stock_data['ts_code'].nunique()}/{total_stocks} 只")
                
                # 显示失败股票统计
                if failed_stocks:
                    print(f"\n⚠ 失败的股票: {len(failed_stocks)} 只")
                    if len(failed_stocks) <= 20:
                        print("   失败列表: " + ", ".join(failed_stocks))
                    else:
                        print(f"   失败列表(前20): " + ", ".join(failed_stocks[:20]))
                        print(f"   ... 还有 {len(failed_stocks) - 20} 只失败股票")
                
                return self.stock_data
                
            except Exception as e:
                print(f"❌ 数据合并失败: {e}")
                return pd.DataFrame()
        else:
            print("❌ 没有获取到任何数据")
            return pd.DataFrame()
    
    def get_multiple_days_data_optimized(self, start_date, end_date, months=3):
        """
        优化版本：自动选择合适的时间范围
        """
        print(f"🎯 智能获取模式：最近{months}个月数据")
        
        # 计算日期范围
        end_date_obj = datetime.strptime(end_date, '%Y%m%d')
        start_date_obj = end_date_obj - timedelta(days=months*30)
        start_date_optimized = start_date_obj.strftime('%Y%m%d')
        
        print(f"📅 优化后的时间范围: {start_date_optimized} 到 {end_date}")
        return self.get_multiple_days_data(start_date_optimized, end_date)
    
    def _check_data_quality(self):
        """检查数据质量"""
        if self.stock_data is None:
            return
        
        print("\n🔍 数据质量检查:")
        print(f"   股票数量: {self.stock_data['ts_code'].nunique()} 只")
        print(f"   交易日数: {self.stock_data['trade_date'].nunique()} 天")
        
        # 检查数据完整性
        stock_count = self.stock_data['ts_code'].nunique()
        date_count = self.stock_data['trade_date'].nunique()
        expected_records = stock_count * date_count
        actual_records = len(self.stock_data)
        completeness = actual_records / expected_records * 100 if expected_records > 0 else 0
        
        print(f"   数据完整度: {completeness:.1f}% ({actual_records}/{expected_records})")
        
        # 检查缺失值
        missing_data = self.stock_data.isnull().sum()
        if missing_data.sum() > 0:
            print("   ⚠ 存在缺失值:")
            for col, count in missing_data.items():
                if count > 0:
                    print(f"     {col}: {count} 个缺失值")
        
        # 检查重复数据
        duplicates = self.stock_data.duplicated().sum()
        if duplicates > 0:
            print(f"   ⚠ 存在 {duplicates} 条重复记录")
            self.stock_data = self.stock_data.drop_duplicates()

    # 其余方法保持不变（get_single_date_data, screen_by_conditions等）
    def get_single_date_data(self, target_date):
        """获取特定日期的全市场数据"""
        try:
            print(f"📅 正在获取 {target_date} 的全市场日线数据...")
            
            self.rate_limiter.wait_if_needed()
            
            for attempt in range(self.retry_times):
                try:
                    df = pro.daily(trade_date=target_date)
                    
                    if not df.empty:
                        df['trade_date'] = pd.to_datetime(df['trade_date'])
                        self.stock_data = df
                        print(f"✅ 获取到 {len(df)} 只股票的数据")
                        return df
                    else:
                        if attempt < self.retry_times - 1:
                            print(f"   ⚠ 第{attempt+1}次获取无数据，重试...")
                            time.sleep(2)
                        else:
                            print(f"❌ {target_date} 无数据（可能是非交易日）")
                            return pd.DataFrame()
                            
                except Exception as e:
                    if attempt < self.retry_times - 1:
                        print(f"   ⚠ 第{attempt+1}次获取失败，重试...")
                        time.sleep(3)
                    else:
                        print(f"❌ 获取单日数据失败: {e}")
                        return pd.DataFrame()
                        
        except Exception as e:
            print(f"❌ 获取单日数据失败: {e}")
            return pd.DataFrame()
    
    def screen_by_conditions(self, conditions_dict):
        """条件筛选"""
        if self.stock_data is None:
            print("请先获取股票数据")
            return None
        
        df = self.stock_data.copy()
        result = df
        
        print("\n正在应用筛选条件...")
        
        # 原有的筛选条件处理逻辑
        if 'date' in conditions_dict:
            date_cond = conditions_dict['date']
            if 'specific_date' in date_cond:
                specific_date = pd.to_datetime(date_cond['specific_date'])
                result = result[result['trade_date'] == specific_date]
                print(f"📅 日期: {specific_date.strftime('%Y-%m-%d')}")
        
        if 'price' in conditions_dict:
            price_cond = conditions_dict['price']
            if 'min_open' in price_cond:
                result = result[result['open'] >= price_cond['min_open']]
                print(f"💰 开盘价 >= {price_cond['min_open']}")
            if 'max_open' in price_cond:
                result = result[result['open'] <= price_cond['max_open']]
                print(f"💰 开盘价 <= {price_cond['max_open']}")
        
        if 'pct_chg' in conditions_dict:
            pct_cond = conditions_dict['pct_chg']
            if 'min_pct' in pct_cond:
                result = result[result['pct_chg'] >= pct_cond['min_pct']]
                print(f"📈 涨跌幅 >= {pct_cond['min_pct']}%")
            if 'direction' in pct_cond and pct_cond['direction'] == 'up':
                result = result[result['pct_chg'] > 0]
                print("📈 筛选上涨股票")
        
        print(f"✅ 筛选完成！找到 {len(result)} 条记录")
        return result

# 其余辅助函数保持不变（rename_columns_to_chinese, display_results, save_results等）
def rename_columns_to_chinese(df):
    """将英文列名转换为中文列名"""
    column_mapping = {
        'ts_code': '股票代码', 'trade_date': '交易日期', 'open': '开盘价',
        'high': '最高价', 'low': '最低价', 'close': '收盘价',
        'pre_close': '昨收价', 'change': '涨跌额', 'pct_chg': '涨跌幅',
        'vol': '成交量', 'amount': '成交额'
    }
    existing_columns = {col: column_mapping[col] for col in df.columns if col in column_mapping}
    return df.rename(columns=existing_columns)

def display_results(result_df, max_display=15):
    """显示结果"""
    if result_df is None or result_df.empty:
        print("❌ 没有找到符合条件的股票")
        return
    
    result_df_chinese = rename_columns_to_chinese(result_df)
    preferred_columns = ['股票代码', '交易日期', '开盘价', '最高价', '最低价', '收盘价', '涨跌幅', '成交量']
    available_columns = [col for col in preferred_columns if col in result_df_chinese.columns]
    
    print(f"\n📋 筛选结果 (显示前{min(max_display, len(result_df))}条):")
    print("="*100)
    print(result_df_chinese[available_columns].head(max_display).to_string(index=False))
    print("="*100)
    
    if '涨跌幅' in result_df_chinese.columns:
        print(f"\n📊 统计信息:")
        print(f"平均涨跌幅: {result_df_chinese['涨跌幅'].mean():.2f}%")
        print(f"上涨股票数量: {len(result_df_chinese[result_df_chinese['涨跌幅'] > 0])}")

def save_results(result_df, filename):
    """保存结果"""
    if result_df is not None and not result_df.empty:
        if not filename.endswith('.csv'):
            filename += '.csv'
        result_df_chinese = rename_columns_to_chinese(result_df)
        result_df_chinese.to_csv(filename, index=False, encoding='utf-8-sig')
        print(f"💾 结果已保存到 {filename}")
        return True
    else:
        print("❌ 没有数据可保存")
        return False

def optimized_interactive_screening():
    """优化后的交互式界面"""
    screener = OptimizedStockScreener()
    
    print("🎯" + "="*60)
    print("           沪深A股全市场股票筛选系统（50只/批优化版）")
    print("="*60)
    print("🎯 特色功能:")
    print("   • 50只股票一批，完美匹配API频率限制")
    print("   • 智能等待策略，最大化获取效率")
    print("   • 实时进度显示，预估完成时间")
    
    while True:
        print("\n📊 请选择数据获取方式:")
        print("1. 获取单日全市场数据（快速）")
        print("2. 获取多日历史数据（50只/批优化）")
        print("3. 智能获取最近3个月数据（推荐）")
        print("4. 设置参数")
        print("5. 退出系统")
        
        choice = input("🖊️  请输入选择 (1-5): ").strip()
        
        if choice == '1':
            optimized_single_date_mode(screener)
        elif choice == '2':
            optimized_multiple_days_mode(screener)
        elif choice == '3':
            smart_multiple_days_mode(screener)
        elif choice == '4':
            settings_mode(screener)
        elif choice == '5':
            print("👋 感谢使用，再见！")
            break
        else:
            print("❌ 无效选择，请重新输入")

def optimized_multiple_days_mode(screener):
    """多日数据获取模式"""
    print("\n📅 多日数据获取模式（50只/批）")
    print("温馨提示：")
    print("   • 每批50只股票，完美利用API限额")
    print("   • 4000只股票约需要80分钟（每批1分钟）")
    print("   • 建议选择3个月以内的数据范围")
    
    start_date = input("请输入开始日期（YYYYMMDD，如20241001）: ").strip()
    end_date = input("请输入结束日期（YYYYMMDD，如20241231）: ").strip()
    
    if not start_date or not end_date:
        print("❌ 请输入有效的日期")
        return
    
    try:
        datetime.strptime(start_date, '%Y%m%d')
        datetime.strptime(end_date, '%Y%m%d')
    except ValueError:
        print("❌ 日期格式错误")
        return
    
    print(f"\n🚀 开始获取数据（50只/批优化模式）...")
    start_time = time.time()
    
    data = screener.get_multiple_days_data(start_date, end_date)
    
    end_time = time.time()
    total_minutes = (end_time - start_time) / 60
    print(f"⏱️ 总耗时: {total_minutes:.1f} 分钟")
    
    if not data.empty:
        screening_loop(screener, f"{start_date}到{end_date}")

def smart_multiple_days_mode(screener):
    """智能获取模式"""
    print("\n🤖 智能获取模式")
    print("自动选择最近3个月数据，平衡数据量和获取时间")
    
    end_date = input("请输入结束日期（YYYYMMDD，回车使用今天）: ").strip()
    if not end_date:
        end_date = datetime.now().strftime('%Y%m%d')
    
    try:
        datetime.strptime(end_date, '%Y%m%d')
    except ValueError:
        print("❌ 日期格式错误")
        return
    
    print(f"\n🚀 开始智能获取数据...")
    start_time = time.time()
    
    data = screener.get_multiple_days_data_optimized(end_date, end_date, months=3)
    
    end_time = time.time()
    total_minutes = (end_time - start_time) / 60
    print(f"⏱️ 总耗时: {total_minutes:.1f} 分钟")
    
    if not data.empty:
        screening_loop(screener, f"最近3个月数据")

# 其余交互函数保持不变...
# （optimized_single_date_mode, settings_mode, screening_loop等函数保持不变）

if __name__ == "__main__":
    try:
        from tqdm import tqdm
        import concurrent.futures
    except ImportError:
        print("❌ 缺少依赖库，请安装: pip install tqdm")
        exit(1)
    
    optimized_interactive_screening()