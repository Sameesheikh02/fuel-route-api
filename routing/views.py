from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .utils import get_optimal_fuel_route

class FuelRouteView(APIView):
    def post(self, request):
        start_location = request.data.get('start')
        end_location = request.data.get('end')

        if not start_location or not end_location:
            return Response({"error": "Please provide 'start' and 'end' locations."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            result = get_optimal_fuel_route(start_location, end_location)
            return Response(result, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)