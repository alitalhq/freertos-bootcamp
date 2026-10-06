#include "timebase.h"
#include "tim.h"
#include "main.h"

void timebase_init(void)
{
    /* MX_TIM2_Init sayacı yalnızca yapılandırır; burada başlatıyoruz.
       Kesme kullanılmıyor, sayaç sadece okunuyor. */
    if (HAL_TIM_Base_Start(&htim2) != HAL_OK)
    {
        Error_Handler();
    }
}
