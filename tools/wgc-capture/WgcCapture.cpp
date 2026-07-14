#ifndef NOMINMAX
#define NOMINMAX
#endif

#include <windows.h>
#include <shobjidl_core.h>
#include <d3d11.h>
#include <dxgi1_2.h>
#include <wincodec.h>
#include <roapi.h>

#include <winrt/base.h>
#include <winrt/Windows.Foundation.h>
#include <winrt/Windows.Graphics.Capture.h>
#include <winrt/Windows.Graphics.DirectX.h>
#include <winrt/Windows.Graphics.DirectX.Direct3D11.h>
#include <windows.graphics.capture.interop.h>
#include <windows.graphics.directx.direct3d11.interop.h>

#include <algorithm>
#include <iostream>
#include <mutex>
#include <string_view>
#include <string>
#include <thread>
#include <utility>
#include <vector>

using namespace winrt;
namespace wgc = winrt::Windows::Graphics::Capture;
namespace wgd = winrt::Windows::Graphics::DirectX;
namespace wgd3d = winrt::Windows::Graphics::DirectX::Direct3D11;
namespace wf = winrt::Windows::Foundation;

namespace
{
    struct WindowCandidate
    {
        HWND hwnd{};
        RECT rect{};
        std::wstring title;
        std::wstring className;
        bool likelyBoss{};
        bool visible{};
        int area{};
    };

    std::string Utf8(std::wstring_view value)
    {
        if (value.empty())
        {
            return "";
        }
        int size = WideCharToMultiByte(CP_UTF8, 0, value.data(), static_cast<int>(value.size()), nullptr, 0, nullptr, nullptr);
        if (size <= 0)
        {
            return "";
        }
        std::string out(static_cast<size_t>(size), '\0');
        WideCharToMultiByte(CP_UTF8, 0, value.data(), static_cast<int>(value.size()), out.data(), size, nullptr, nullptr);
        return out;
    }

    HWND CreateOwnerWindow()
    {
        WNDCLASSW wc{};
        wc.lpfnWndProc = DefWindowProcW;
        wc.hInstance = GetModuleHandleW(nullptr);
        wc.lpszClassName = L"WgcCaptureOwnerWindow";
        RegisterClassW(&wc);

        HWND hwnd = CreateWindowExW(
            WS_EX_TOOLWINDOW,
            wc.lpszClassName,
            L"WGC Capture Owner - select BOSS",
            WS_POPUP,
            CW_USEDEFAULT,
            CW_USEDEFAULT,
            1,
            1,
            nullptr,
            nullptr,
            wc.hInstance,
            nullptr);
        return hwnd;
    }

    wgd3d::IDirect3DDevice CreateWinRTDevice(winrt::com_ptr<ID3D11Device> const& d3dDevice)
    {
        winrt::com_ptr<IDXGIDevice> dxgiDevice;
        check_hresult(d3dDevice->QueryInterface(IID_PPV_ARGS(dxgiDevice.put())));

        winrt::com_ptr<::IInspectable> inspectable;
        check_hresult(CreateDirect3D11DeviceFromDXGIDevice(dxgiDevice.get(), inspectable.put()));
        return inspectable.as<wgd3d::IDirect3DDevice>();
    }

    winrt::com_ptr<ID3D11Device> CreateD3DDevice()
    {
        UINT flags = D3D11_CREATE_DEVICE_BGRA_SUPPORT;
        D3D_FEATURE_LEVEL levels[] = {
            D3D_FEATURE_LEVEL_11_1,
            D3D_FEATURE_LEVEL_11_0,
            D3D_FEATURE_LEVEL_10_1,
            D3D_FEATURE_LEVEL_10_0,
        };
        winrt::com_ptr<ID3D11Device> device;
        winrt::com_ptr<ID3D11DeviceContext> context;
        D3D_FEATURE_LEVEL level{};
        check_hresult(D3D11CreateDevice(
            nullptr,
            D3D_DRIVER_TYPE_HARDWARE,
            nullptr,
            flags,
            levels,
            ARRAYSIZE(levels),
            D3D11_SDK_VERSION,
            device.put(),
            &level,
            context.put()));
        return device;
    }

    winrt::com_ptr<ID3D11Texture2D> GetTextureFromSurface(wgd3d::IDirect3DSurface const& surface)
    {
        auto access = surface.as<::Windows::Graphics::DirectX::Direct3D11::IDirect3DDxgiInterfaceAccess>();
        winrt::com_ptr<ID3D11Texture2D> texture;
        check_hresult(access->GetInterface(IID_PPV_ARGS(texture.put())));
        return texture;
    }

    wgc::GraphicsCaptureItem CreateItemForWindow(HWND hwnd)
    {
        auto factory = winrt::get_activation_factory<wgc::GraphicsCaptureItem>();
        auto interop = factory.as<IGraphicsCaptureItemInterop>();

        wgc::GraphicsCaptureItem item{ nullptr };
        check_hresult(interop->CreateForWindow(hwnd, winrt::guid_of<wgc::GraphicsCaptureItem>(), winrt::put_abi(item)));
        return item;
    }

    void SaveTextureAsPng(winrt::com_ptr<ID3D11Device> const& device, winrt::com_ptr<ID3D11Texture2D> const& texture, std::wstring const& path)
    {
        D3D11_TEXTURE2D_DESC desc{};
        texture->GetDesc(&desc);

        D3D11_TEXTURE2D_DESC stagingDesc = desc;
        stagingDesc.BindFlags = 0;
        stagingDesc.MiscFlags = 0;
        stagingDesc.CPUAccessFlags = D3D11_CPU_ACCESS_READ;
        stagingDesc.Usage = D3D11_USAGE_STAGING;

        winrt::com_ptr<ID3D11Texture2D> staging;
        check_hresult(device->CreateTexture2D(&stagingDesc, nullptr, staging.put()));

        winrt::com_ptr<ID3D11DeviceContext> context;
        device->GetImmediateContext(context.put());
        context->CopyResource(staging.get(), texture.get());

        D3D11_MAPPED_SUBRESOURCE mapped{};
        check_hresult(context->Map(staging.get(), 0, D3D11_MAP_READ, 0, &mapped));

        winrt::com_ptr<IWICImagingFactory> factory;
        check_hresult(CoCreateInstance(CLSID_WICImagingFactory, nullptr, CLSCTX_INPROC_SERVER, IID_PPV_ARGS(factory.put())));

        winrt::com_ptr<IWICStream> stream;
        check_hresult(factory->CreateStream(stream.put()));
        check_hresult(stream->InitializeFromFilename(path.c_str(), GENERIC_WRITE));

        winrt::com_ptr<IWICBitmapEncoder> encoder;
        check_hresult(factory->CreateEncoder(GUID_ContainerFormatPng, nullptr, encoder.put()));
        check_hresult(encoder->Initialize(stream.get(), WICBitmapEncoderNoCache));

        winrt::com_ptr<IWICBitmapFrameEncode> frame;
        check_hresult(encoder->CreateNewFrame(frame.put(), nullptr));
        check_hresult(frame->Initialize(nullptr));
        check_hresult(frame->SetSize(desc.Width, desc.Height));

        WICPixelFormatGUID format = GUID_WICPixelFormat32bppBGRA;
        check_hresult(frame->SetPixelFormat(&format));
        check_hresult(frame->WritePixels(desc.Height, mapped.RowPitch, mapped.RowPitch * desc.Height, static_cast<BYTE*>(mapped.pData)));
        check_hresult(frame->Commit());
        check_hresult(encoder->Commit());

        context->Unmap(staging.get(), 0);
    }

    bool WaitWithMessagePump(HANDLE eventHandle, DWORD timeoutMs)
    {
        DWORD start = GetTickCount();
        MSG msg{};
        while (true)
        {
            DWORD elapsed = GetTickCount() - start;
            if (elapsed >= timeoutMs)
            {
                return false;
            }

            DWORD wait = MsgWaitForMultipleObjects(1, &eventHandle, FALSE, timeoutMs - elapsed, QS_ALLINPUT);
            if (wait == WAIT_OBJECT_0)
            {
                return true;
            }
            if (wait == WAIT_OBJECT_0 + 1)
            {
                while (PeekMessageW(&msg, nullptr, 0, 0, PM_REMOVE))
                {
                    TranslateMessage(&msg);
                    DispatchMessageW(&msg);
                }
                continue;
            }
            return false;
        }
    }

    std::wstring WindowText(HWND hwnd)
    {
        wchar_t text[512]{};
        GetWindowTextW(hwnd, text, 512);
        return text;
    }

    std::wstring WindowClass(HWND hwnd)
    {
        wchar_t text[256]{};
        GetClassNameW(hwnd, text, 256);
        return text;
    }

    HWND FindBossChromeWidgetWindow()
    {
        std::vector<WindowCandidate> candidates;
        EnumWindows([](HWND hwnd, LPARAM lparam) -> BOOL
        {
            auto& items = *reinterpret_cast<std::vector<WindowCandidate>*>(lparam);
            auto cls = WindowClass(hwnd);
            auto title = WindowText(hwnd);
            bool chromeWidget = cls.find(L"Chrome_WidgetWin_0") != std::wstring::npos ||
                cls.find(L"Chrome_WidgetWin_1") != std::wstring::npos;
            if (!chromeWidget)
            {
                return TRUE;
            }

            bool likelyBoss = title.find(L"BOSS") != std::wstring::npos ||
                title.find(L"直聘") != std::wstring::npos ||
                title.find(L"zhipin") != std::wstring::npos;
            bool visible = IsWindowVisible(hwnd);
            RECT rect{};
            if (!GetWindowRect(hwnd, &rect))
            {
                return TRUE;
            }
            int width = rect.right - rect.left;
            int height = rect.bottom - rect.top;
            bool usableSize = width >= 600 && height >= 400;
            if (!likelyBoss && (!visible || !usableSize))
            {
                return TRUE;
            }

            items.push_back(WindowCandidate{ hwnd, rect, title, cls, likelyBoss, visible, width * height });
            return TRUE;
        }, reinterpret_cast<LPARAM>(&candidates));

        if (candidates.empty())
        {
            std::cerr << "No visible Chrome_WidgetWin_0/1 candidates found.\n";
            return nullptr;
        }

        std::sort(candidates.begin(), candidates.end(), [](auto const& a, auto const& b)
        {
            if (a.likelyBoss != b.likelyBoss)
            {
                return a.likelyBoss > b.likelyBoss;
            }
            if (a.visible != b.visible)
            {
                return a.visible > b.visible;
            }
            return a.area > b.area;
        });

        std::cout << "Chrome widget candidates:\n";
        for (auto const& candidate : candidates)
        {
            std::cout << "  hwnd=0x" << std::hex << reinterpret_cast<uintptr_t>(candidate.hwnd) << std::dec
                << " class=" << Utf8(candidate.className)
                << " title=\"" << Utf8(candidate.title) << "\""
                << " rect=(" << candidate.rect.left << "," << candidate.rect.top << "," << candidate.rect.right << "," << candidate.rect.bottom << ")"
                << (candidate.likelyBoss ? " likelyBoss" : "")
                << (candidate.visible ? " visible" : " hidden")
                << "\n";
        }

        if (!candidates.front().likelyBoss)
        {
            std::cerr << "No visible Chrome_WidgetWin candidate matched BOSS/zhipin.\n";
            return nullptr;
        }

        return candidates.front().hwnd;
    }

    void ClickRelative(HWND hwnd, double xRatio, double yRatio)
    {
        if (!hwnd)
        {
            throw_hresult(HRESULT_FROM_WIN32(ERROR_INVALID_WINDOW_HANDLE));
        }

        ShowWindow(hwnd, SW_RESTORE);
        SetForegroundWindow(hwnd);
        std::this_thread::sleep_for(std::chrono::milliseconds(300));

        RECT rect{};
        if (!GetWindowRect(hwnd, &rect))
        {
            throw_hresult(HRESULT_FROM_WIN32(ERROR_INVALID_WINDOW_HANDLE));
        }

        int width = rect.right - rect.left;
        int height = rect.bottom - rect.top;
        int x = rect.left + static_cast<int>(width * xRatio);
        int y = rect.top + static_cast<int>(height * yRatio);
        SetCursorPos(x, y);

        INPUT inputs[2]{};
        inputs[0].type = INPUT_MOUSE;
        inputs[0].mi.dwFlags = MOUSEEVENTF_LEFTDOWN;
        inputs[1].type = INPUT_MOUSE;
        inputs[1].mi.dwFlags = MOUSEEVENTF_LEFTUP;
        SendInput(2, inputs, sizeof(INPUT));
    }

    class PersistentCapture
    {
    public:
        PersistentCapture(
            wgc::GraphicsCaptureItem const& item,
            winrt::com_ptr<ID3D11Device> d3dDevice,
            wgd3d::IDirect3DDevice const& winrtDevice)
            : m_item(item), m_d3dDevice(std::move(d3dDevice))
        {
            auto size = m_item.Size();
            if (size.Width <= 0 || size.Height <= 0)
            {
                throw_hresult(E_INVALIDARG);
            }

            std::wcout << L"Capture item size: " << size.Width << L"x" << size.Height << L"\n";

            m_frameEvent.attach(CreateEventW(nullptr, FALSE, FALSE, nullptr));
            if (!m_frameEvent)
            {
                check_hresult(HRESULT_FROM_WIN32(GetLastError()));
            }

            m_framePool = wgc::Direct3D11CaptureFramePool::CreateFreeThreaded(
                winrtDevice,
                wgd::DirectXPixelFormat::B8G8R8A8UIntNormalized,
                2,
                size);

            m_frameArrived = m_framePool.FrameArrived(winrt::auto_revoke, [this](wgc::Direct3D11CaptureFramePool const& sender, auto const&)
            {
                wgc::Direct3D11CaptureFrame latest{ nullptr };
                while (auto frame = sender.TryGetNextFrame())
                {
                    latest = frame;
                }

                if (latest)
                {
                    {
                        std::lock_guard<std::mutex> lock(m_mutex);
                        m_latestFrame = latest;
                        ++m_frameCount;
                    }
                    SetEvent(m_frameEvent.get());
                }
            });

            m_session = m_framePool.CreateCaptureSession(m_item);
            m_session.IsCursorCaptureEnabled(false);
            m_session.StartCapture();
            std::wcout << L"Capture session started; waiting for first frame...\n";
            if (!WaitForFrame(15000))
            {
                std::wcerr << L"Timed out waiting for initial capture frame.\n";
                throw_hresult(HRESULT_FROM_WIN32(WAIT_TIMEOUT));
            }
        }

        ~PersistentCapture()
        {
            try
            {
                m_frameArrived.revoke();
                if (m_session)
                {
                    m_session.Close();
                }
                if (m_framePool)
                {
                    m_framePool.Close();
                }
            }
            catch (...)
            {
            }
        }

        bool WaitForFrame(DWORD timeoutMs)
        {
            if (HasFrame())
            {
                return true;
            }
            return WaitWithMessagePump(m_frameEvent.get(), timeoutMs) && HasFrame();
        }

        bool WaitForNewFrame(uint64_t previousFrameCount, DWORD timeoutMs)
        {
            if (FrameCount() > previousFrameCount)
            {
                return true;
            }

            DWORD start = GetTickCount();
            while (true)
            {
                DWORD elapsed = GetTickCount() - start;
                if (elapsed >= timeoutMs)
                {
                    return FrameCount() > previousFrameCount;
                }

                if (!WaitWithMessagePump(m_frameEvent.get(), timeoutMs - elapsed))
                {
                    return FrameCount() > previousFrameCount;
                }
                if (FrameCount() > previousFrameCount)
                {
                    return true;
                }
            }
        }

        uint64_t FrameCount()
        {
            std::lock_guard<std::mutex> lock(m_mutex);
            return m_frameCount;
        }

        void SaveLatest(std::wstring const& output)
        {
            wgc::Direct3D11CaptureFrame frame{ nullptr };
            {
                std::lock_guard<std::mutex> lock(m_mutex);
                frame = m_latestFrame;
            }

            if (!frame)
            {
                std::wcerr << L"No capture frame available.\n";
                throw_hresult(HRESULT_FROM_WIN32(WAIT_TIMEOUT));
            }

            auto texture = GetTextureFromSurface(frame.Surface());
            SaveTextureAsPng(m_d3dDevice, texture, output);
        }

    private:
        bool HasFrame()
        {
            std::lock_guard<std::mutex> lock(m_mutex);
            return m_latestFrame != nullptr;
        }

        wgc::GraphicsCaptureItem m_item{ nullptr };
        winrt::com_ptr<ID3D11Device> m_d3dDevice;
        wgc::Direct3D11CaptureFramePool m_framePool{ nullptr };
        wgc::GraphicsCaptureSession m_session{ nullptr };
        wgc::Direct3D11CaptureFrame m_latestFrame{ nullptr };
        wgc::Direct3D11CaptureFramePool::FrameArrived_revoker m_frameArrived;
        winrt::handle m_frameEvent;
        std::mutex m_mutex;
        uint64_t m_frameCount{};
    };
}

int wmain(int argc, wchar_t** argv)
{
    bool scanMode = argc > 1 && wcscmp(argv[1], L"--scan") == 0;
    bool autoBossMode = argc > 1 && wcscmp(argv[1], L"--auto-boss") == 0;
    std::wstring output = argc > 1 ? argv[1] : L"boss.png";
    std::wstring scanDir = L"boss-scan";
    int scanCount = 5;
    if (scanMode)
    {
        scanDir = argc > 2 ? argv[2] : L"boss-scan";
        scanCount = argc > 3 ? std::max(1, _wtoi(argv[3])) : 5;
    }
    else if (autoBossMode)
    {
        output = argc > 2 ? argv[2] : L"boss.png";
    }

    try
    {
        winrt::init_apartment(winrt::apartment_type::single_threaded);

        if (!wgc::GraphicsCaptureSession::IsSupported())
        {
            std::wcerr << L"Windows Graphics Capture is not supported on this system.\n";
            return 2;
        }

        wgc::GraphicsCaptureItem item{ nullptr };
        HWND owner{};
        HWND bossWindow{};
        HWND previousForeground = GetForegroundWindow();

        if (scanMode || autoBossMode)
        {
            bossWindow = FindBossChromeWidgetWindow();
            if (!bossWindow)
            {
                std::cerr << "Could not find a visible Chrome_WidgetWin BOSS window.\n";
                return 6;
            }

            if (scanMode)
            {
                ShowWindow(bossWindow, SW_RESTORE);
                SetForegroundWindow(bossWindow);
                std::this_thread::sleep_for(std::chrono::milliseconds(500));
            }
            else
            {
                if (IsIconic(bossWindow))
                {
                    ShowWindow(bossWindow, SW_RESTORE);
                    std::this_thread::sleep_for(std::chrono::milliseconds(500));
                }
                else
                {
                    std::this_thread::sleep_for(std::chrono::milliseconds(150));
                }
            }
            item = CreateItemForWindow(bossWindow);
        }
        else
        {
            owner = CreateOwnerWindow();
            wgc::GraphicsCapturePicker picker;
            auto initializeWithWindow = picker.as<IInitializeWithWindow>();
            check_hresult(initializeWithWindow->Initialize(owner));

            std::cout << "Select the BOSS window in the picker...\n";
            HANDLE pickerEvent = CreateEventW(nullptr, TRUE, FALSE, nullptr);
            if (!pickerEvent)
            {
                check_hresult(HRESULT_FROM_WIN32(GetLastError()));
            }

            auto pickOperation = picker.PickSingleItemAsync();
            pickOperation.Completed([&](auto const& asyncInfo, wf::AsyncStatus status)
            {
                if (status == wf::AsyncStatus::Completed)
                {
                    item = asyncInfo.GetResults();
                }
                SetEvent(pickerEvent);
            });

            if (!WaitWithMessagePump(pickerEvent, 120000))
            {
                std::cerr << "Timed out waiting for picker selection.\n";
                CloseHandle(pickerEvent);
                DestroyWindow(owner);
                return 5;
            }
            CloseHandle(pickerEvent);
            if (!item)
            {
                std::cerr << "No capture item selected.\n";
                DestroyWindow(owner);
                return 3;
            }
        }

        auto selectedSize = item.Size();
        if (selectedSize.Width < 600 || selectedSize.Height < 400)
        {
            std::cerr << "Selected item is too small (" << selectedSize.Width << "x" << selectedSize.Height
                << "). Select the main BOSS chat window, not a toolbar, popup, or title area.\n";
            if (owner)
            {
                DestroyWindow(owner);
            }
            return 7;
        }

        auto d3dDevice = CreateD3DDevice();
        auto winrtDevice = CreateWinRTDevice(d3dDevice);
        PersistentCapture capture(item, d3dDevice, winrtDevice);

        if (!scanMode)
        {
            capture.SaveLatest(output);
            std::cout << "Saved: " << Utf8(output) << "\n";
        }
        else
        {
            CreateDirectoryW(scanDir.c_str(), nullptr);

            constexpr double chatX = 0.18;
            constexpr double firstRowY = 0.265;
            constexpr double rowStepY = 0.093;
            for (int i = 0; i < scanCount; ++i)
            {
                double y = firstRowY + rowStepY * i;
                if (y > 0.90)
                {
                    break;
                }

                uint64_t beforeClickFrame = capture.FrameCount();
                ClickRelative(bossWindow, chatX, y);
                std::this_thread::sleep_for(std::chrono::milliseconds(1200));
                if (!capture.WaitForNewFrame(beforeClickFrame, 5000))
                {
                    std::cerr << "Warning: no fresh frame observed after click; saving the latest available frame.\n";
                }

                std::wstring path = scanDir + L"\\boss_" + std::to_wstring(i + 1) + L".png";
                capture.SaveLatest(path);
                std::cout << "Saved: " << Utf8(path) << "\n";
            }

            if (previousForeground && previousForeground != bossWindow && IsWindow(previousForeground))
            {
                SetForegroundWindow(previousForeground);
            }
        }

        if (owner)
        {
            DestroyWindow(owner);
        }
        return 0;
    }
    catch (winrt::hresult_error const& e)
    {
        std::wcerr << L"Capture failed: 0x" << std::hex << static_cast<uint32_t>(e.code()) << L" " << e.message().c_str() << L"\n";
        return 1;
    }
}
